# Changelog

## 1.1.0
- Fixed "can't find address" searches. Search now asks three geocoders at once
  (US Census, OpenStreetMap Nominatim, Photon) and merges the results.
- Outbound lookups are forced to IPv4, which fixes hangs on some Docker/HAOS networks.
- When nothing is found, the real error from each provider is shown instead of a vague message.
- You can paste "lat, lon" into the search box to jump straight to a point.
- Added icon, logo, docs, and config option labels.

## 1.0.0
- First release: address search, draggable pin with live radius circle,
  optional AI name and icon suggestions, one-tap zone creation.
