worker_processes 1;
pid /run/nginx/nginx.pid;
error_log /dev/stderr __NGINX_LOG_LEVEL__;

events {
    worker_connections 1024;
}

http {
    access_log off;
    default_type application/octet-stream;
    client_max_body_size 0;

    map $http_upgrade $connection_upgrade {
        default upgrade;
        ''      close;
    }

    # X-Ingress-Path without any trailing slash
    map $http_x_ingress_path $ingress_base {
        "~^(?<ibase>.*?)/*$" $ibase;
    }

    server {
        listen 8099;

        # Only the Home Assistant Supervisor may talk to the ingress port
        allow 172.30.32.2;
        deny all;

        location = /__ingress_shim.js {
            alias /etc/nginx/ingress-shim.js;
            default_type application/javascript;
            add_header Cache-Control "no-cache";
        }

        location / {
            proxy_pass http://127.0.0.1:8000;
            proxy_http_version 1.1;
            proxy_set_header Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $connection_upgrade;
            proxy_set_header Accept-Encoding "";
            proxy_buffering off;
            proxy_request_buffering off;
            proxy_read_timeout 3600s;
            proxy_send_timeout 3600s;

            # SillyTavern has no base-path support, so absolute URLs in HTML/CSS
            # are rewritten to live under the ingress path. JavaScript-created
            # URLs are handled by ingress-shim.js.
            sub_filter_once off;
            sub_filter_types text/html text/css;

            sub_filter '<head>' '<head><script type="importmap">{"imports":{"/script.js":"$ingress_base/script.js","/lib.js":"$ingress_base/lib.js","/scripts/":"$ingress_base/scripts/","/lib/":"$ingress_base/lib/"}}</script><script src="$ingress_base/__ingress_shim.js"></script>';

            sub_filter 'href="/'  'href="$ingress_base/';
            sub_filter "href='/"  "href='$ingress_base/";
            sub_filter 'src="/'   'src="$ingress_base/';
            sub_filter "src='/"   "src='$ingress_base/";
            sub_filter 'action="/' 'action="$ingress_base/';
            sub_filter "action='/" "action='$ingress_base/";
            sub_filter 'url(/'    'url($ingress_base/';
            sub_filter 'url("/'   'url("$ingress_base/';
            sub_filter "url('/"   "url('$ingress_base/";
        }
    }
}
