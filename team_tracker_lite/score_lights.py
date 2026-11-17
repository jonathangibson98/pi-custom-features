"""Score lights for Team Tracker Lite (was the sports_score_lights AppDaemon app).

Two groups of lights show the teams' colors and swap between the two teams every so often. When a team scores
(a field goal or touchdown in football, any score in most other sports), the groups flash that team's colors.
When your team wins, they celebrate. Everything is set on the add-on page; it never needs AppDaemon.
"""
import json
import os
import threading
import time

DEFAULTS = {"enabled": False, "group1": [], "group2": [], "condition_entity": "", "condition_state": "",
            "alternate_seconds": 30, "flash_count": 3, "flash_interval": 0.8, "brightness": 100,
            "flash_on": "big", "celebrate_win": True, "only_game_day": True}
WHITE_SUB, BLACK_SUB = [207, 232, 255], [61, 43, 0]   # bulb-friendly stand-ins for white and black team colors


def rgb(h):
    h = str(h or "").lstrip("#")
    try:
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    except ValueError:
        return None


def usable(colors):
    out = []
    for c in colors or []:
        v = rgb(c)
        if v is None:
            continue
        if all(x >= 235 for x in v):
            v = WHITE_SUB
        elif all(x <= 20 for x in v):
            v = BLACK_SUB
        out.append(v)
    if len(out) == 1:
        out.append([min(255, int(x * 0.45)) for x in out[0]])  # a darker shade as the second color
    return out


class ScoreLights:
    def __init__(self, get_settings, get_sensor, call, log, state_file):
        self.get_settings, self.get_sensor, self.call, self.log = get_settings, get_sensor, call, log
        self.state_file = state_file
        self.mem = self._load()
        self.side = 0
        self.next_swap = 0.0
        self.busy = False
        self.cond_cache = (0.0, None)
        self.status = "off"

    def _load(self):
        try:
            with open(self.state_file) as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return {}

    def _save(self):
        try:
            with open(self.state_file, "w") as f:
                json.dump(self.mem, f)
        except OSError:
            pass

    def cfg(self):
        c = dict(DEFAULTS)
        c.update(self.get_settings().get("score_lights") or {})
        return c

    def condition_ok(self, c):
        if not c["condition_entity"]:
            return True
        t, val = self.cond_cache
        if time.time() - t > 5:
            try:
                val = (self.call("GET", "/core/api/states/" + c["condition_entity"]) or {}).get("state")
            except Exception:  # noqa: BLE001
                val = None
            self.cond_cache = (time.time(), val)
        return str(val) == str(c["condition_state"])

    def paint(self, c, colors):
        """Group 1 = first color, group 2 = second color."""
        b = max(1, min(100, int(c["brightness"])))
        for grp, col in ((c["group1"], colors[0] if colors else None), (c["group2"], colors[1] if len(colors) > 1 else (colors[0] if colors else None))):
            if grp and col:
                try:
                    self.call("POST", "/core/api/services/light/turn_on", {"entity_id": grp, "rgb_color": col, "brightness_pct": b, "transition": 1})
                except Exception as e:  # noqa: BLE001
                    self.log("warning", "Score lights: couldn't set lights:", e)

    def flash(self, c, colors, times=None, interval=None):
        if not colors:
            return
        self.busy = True
        try:
            a, b = colors[0], colors[1] if len(colors) > 1 else colors[0]
            for k in range((times or int(c["flash_count"])) * 2):
                pair = (a, b) if k % 2 == 0 else (b, a)
                self.paint(dict(c, brightness=100), list(pair))
                time.sleep(max(0.5, float(interval or c["flash_interval"])))
        finally:
            self.busy = False
            self.next_swap = 0  # repaint the steady colors right away

    def is_flashable(self, sport, delta, mode):
        if delta <= 0:
            return False
        if mode == "every":
            return True
        if sport == "football":
            return delta == 3 or delta >= 6   # field goal or touchdown, not the extra point on its own
        if sport == "basketball":
            return delta >= 3                  # threes only, or the lights never stop
        return True

    def test(self):
        c = self.cfg()
        a = (self.get_sensor() or {}).get("attributes") or {}
        cols = usable(a.get("team_colors")) or [[255, 0, 0], [0, 80, 255]]
        threading.Thread(target=self.flash, args=(c, cols), daemon=True).start()

    def tick(self):
        c = self.cfg()
        sensor = self.get_sensor() or {}
        st, a = sensor.get("state"), sensor.get("attributes") or {}
        if not c["enabled"] or not (c["group1"] or c["group2"]):
            self.status = "off"
            return
        if not self.condition_ok(c):
            self.status = "waiting for %s = %s" % (c["condition_entity"], c["condition_state"])
            return
        if c["only_game_day"] and st not in ("PRE", "IN", "POST"):
            self.status = "no game"
            return
        if c["only_game_day"] and st == "PRE" and "day" in str(a.get("kickoff_in") or "") and "today" not in str(a.get("kickoff_in") or "").lower():
            self.status = "game isn't today"
            return
        ev = str(a.get("event_name") or "") + str(a.get("date") or "")
        mine = self.mem.get("event") == ev
        ts, os_ = a.get("team_score"), a.get("opponent_score")
        team_cols, opp_cols = usable(a.get("team_colors")), usable(a.get("opponent_colors"))
        if not team_cols:
            team_cols = [[255, 255, 255], [120, 120, 120]]
        if not opp_cols:
            opp_cols = [[255, 60, 0], [120, 20, 0]]
        if not mine:
            self.mem = {"event": ev, "team": ts, "opp": os_, "won": False}
            self._save()
        elif isinstance(ts, int) and isinstance(os_, int) and not self.busy:
            sport = str(a.get("sport") or "")
            dt = ts - (self.mem.get("team") if isinstance(self.mem.get("team"), int) else ts)
            do = os_ - (self.mem.get("opp") if isinstance(self.mem.get("opp"), int) else os_)
            if dt != 0 or do != 0:
                self.mem.update(team=ts, opp=os_)
                self._save()
                if self.is_flashable(sport, dt, c["flash_on"]):
                    self.log("info", "Score lights: %s scored (+%d)" % (a.get("team_name"), dt))
                    threading.Thread(target=self.flash, args=(c, team_cols), daemon=True).start()
                    return
                if self.is_flashable(sport, do, c["flash_on"]):
                    self.log("info", "Score lights: %s scored (+%d)" % (a.get("opponent_name"), do))
                    threading.Thread(target=self.flash, args=(c, opp_cols), daemon=True).start()
                    return
        if st == "POST" and a.get("team_winner") and c["celebrate_win"] and not self.mem.get("won") and not self.busy:
            self.mem["won"] = True
            self._save()
            self.log("info", "Score lights: %s won! Celebrating." % a.get("team_name"))
            threading.Thread(target=self.flash, args=(c, team_cols, 8, 0.7), daemon=True).start()
            return
        if self.busy:
            return
        self.status = "showing %s" % (a.get("team_name") if self.side == 0 else a.get("opponent_name"))
        if time.time() >= self.next_swap:
            self.paint(c, team_cols if self.side == 0 else opp_cols)
            self.side = 1 - self.side
            self.next_swap = time.time() + max(5, int(c["alternate_seconds"]))

    def run(self):
        while True:
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001
                self.log("warning", "Score lights:", e)
            time.sleep(1)
