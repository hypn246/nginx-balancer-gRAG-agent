# How to use load balancing method in Nginx

**Updated:** July 24, 2026 (Originally published: January 23, 2026)

NGINX load balancing distributes incoming traffic across multiple backend servers to improve performance, reliability, and scalability. This comprehensive guide covers everything from basic round-robin to advanced algorithms like consistent hashing and the Power of Two Choices.

Unlike many tutorials that blindly copy-paste configurations, we’ll examine what actually happens under the hood by looking at NGINX source code. Understanding the internals helps you make informed decisions about which load balancing method fits your workload.

## What is Load Balancing in NGINX?

Load balancing is the process of distributing network traffic across multiple servers. When you configure NGINX load balancing, it acts as a reverse proxy, accepting client requests and forwarding them to backend servers based on a configured algorithm.

The benefits include:

- **High availability** – If one server fails, traffic routes to healthy servers
- **Horizontal scalability** – Add more servers to handle increased load
- **Better resource utilization** – Spread work evenly across infrastructure
- **Reduced latency** – Route users to the fastest available server
- **Zero-downtime deployments** – Remove servers from rotation during updates

NGINX handles load balancing through the `upstream` block directive. Here’s a minimal example:

```
upstream backend {
    server 192.168.1.10:8080;
    server 192.168.1.11:8080;
    server 192.168.1.12:8080;
}

server {
    listen 80;
    location / {
        proxy_pass <http://backend>;
    }
}
```

This configuration distributes requests across three backend servers using the default round-robin algorithm.

## NGINX Load Balancing Algorithms

NGINX provides six algorithms for distributing traffic. Each has specific use cases and trade-offs. Choosing the right one depends on your application’s characteristics.

### Round-Robin (Default)

When no algorithm is specified, NGINX uses weighted round-robin. Requests cycle through servers in order, with each server receiving traffic proportional to its weight.

```
upstream backend {
    server 192.168.1.10:8080;
    server 192.168.1.11:8080;
    server 192.168.1.12:8080;
}
```

**How it works internally:** NGINX maintains three weight values for each server: `weight`, `effective_weight`, and `current_weight`. The algorithm selects the server with the highest `current_weight`, then reduces that weight by the total weight of all servers. This ensures perfect distribution over time.

**When to use round-robin:**

- Stateless applications where any server can handle any request
- Homogeneous server environments with similar capacity
- Simple deployments without complex session requirements

### Weighted Round-Robin

Assign different weights to servers based on their capacity. A server with `weight=5` receives five times more traffic than a server with `weight=1`.

```
upstream backend {
    server 192.168.1.10:8080 weight=5;  # 50% of traffic
    server 192.168.1.11:8080 weight=3;  # 30% of traffic
    server 192.168.1.12:8080 weight=2;  # 20% of traffic
}
```

**Calculating weights:** Base weights on actual server capacity. If server A has 16 CPU cores and server B has 8 cores, assign `weight=2` and `weight=1` respectively.

**When to use weighted round-robin:**

- Mixed hardware environments with different server capacities
- Gradual traffic shifting during migrations
- Canary deployments where new versions receive limited traffic

### Least Connections

The `least_conn` directive routes each request to the server with the fewest active connections. This method works well when request processing times vary significantly.

```
upstream backend {
    least_conn;
    server 192.168.1.10:8080;
    server 192.168.1.11:8080;
    server 192.168.1.12:8080;
}
```

**How it works internally:** NGINX tracks active connections per server in the `conns` field. The selection formula accounts for weights: `peer->conns * best->weight < best->conns * peer->weight`. When multiple servers have equal weighted connections, round-robin breaks the tie.

**Combining with weights:**

```
upstream backend {
    least_conn;
    server 192.168.1.10:8080 weight=5;
    server 192.168.1.11:8080 weight=3;
    server 192.168.1.12:8080 weight=2;
}
```

The weighted comparison ensures higher-capacity servers accept proportionally more connections.

**When to use least connections:**

- Long-lived connections like WebSockets
- Requests with highly variable processing times
- API endpoints where some calls take much longer than others

### IP Hash

The `ip_hash` directive ensures requests from the same client IP always go to the same server, providing session persistence without application-level session storage.

```
upstream backend {
    ip_hash;
    server 192.168.1.10:8080;
    server 192.168.1.11:8080;
    server 192.168.1.12:8080;
}
```

**How it works internally:** NGINX computes a hash using the formula `hash = (hash * 113 + addr[i]) % 6271` with an initial hash value of 89. For IPv4, only the first three octets are used (the `/24` subnet), so clients from the same subnet route to the same server. For IPv6, all 16 bytes are hashed.

**Important limitation:** If a server goes down, clients previously routed to it get redistributed. When the server returns, those clients switch back, potentially disrupting active sessions.

**When to use IP hash:**

- Applications with server-side session storage
- Legacy systems that cannot share sessions across servers
- Scenarios where sticky sessions are required but cookies aren’t viable

### Generic Hash

The `hash` directive computes a hash from a configurable key. This provides more flexibility than IP hash.

```
upstream backend {
    hash $request_uri;
    server 192.168.1.10:8080;
    server 192.168.1.11:8080;
    server 192.168.1.12:8080;
}
```

You can hash any combination of NGINX variables:

```
upstream backend {
    hash $scheme$host$request_uri;
    server 192.168.1.10:8080;
    server 192.168.1.11:8080;
    server 192.168.1.12:8080;
}
```

**How it works internally:** NGINX uses CRC32 for hashing, with the expression `((crc32([REHASH] KEY) >> 16) & 0x7fff) + PREV_HASH`. This is compatible with Cache::Memcached, making it useful for distributed caching scenarios.

**When to use generic hash:**

- Content-based routing (same URL always hits same cache server)
- User-based routing with custom session identifiers
- Distributed caching where cache locality matters

### Consistent Hashing

Add the `consistent` parameter to enable consistent hashing, which minimizes redistribution when servers are added or removed from your upstream pool.

```
upstream backend {
    hash $request_uri consistent;
    server 192.168.1.10:8080;
    server 192.168.1.11:8080;
    server 192.168.1.12:8080;
}
```

**How it works internally:** NGINX creates 160 virtual nodes per weight unit for each server. These nodes are distributed around a hash ring. When a request arrives, NGINX hashes the key and finds the nearest virtual node using binary search.

**Impact of server changes:** With standard hashing, adding or removing a server redistributes most keys. With consistent hashing, only keys that would map to the changed server are affected, typically `1/n` of total keys where `n` is the number of servers.

**When to use consistent hashing:**

- Distributed caching where cache invalidation is expensive
- Stateful services where session migration has high overhead
- Any scenario where minimizing redistribution during scaling matters

### Random

The `random` directive selects a server randomly, weighted by server weights.

```
upstream backend {
    random;
    server 192.168.1.10:8080;
    server 192.168.1.11:8080;
    server 192.168.1.12:8080;
}
```

**How it works internally:** NGINX uses `ngx_random() % total_weight` to select a server. A binary search finds which server’s weight range contains the random value.

### Random with Power of Two Choices

The `random two least_conn` configuration implements the “Power of Two Choices” algorithm, which provides near-optimal load distribution with minimal overhead.

```
upstream backend {
    random two least_conn;
    server 192.168.1.10:8080;
    server 192.168.1.11:8080;
    server 192.168.1.12:8080;
}
```

**How it works internally:** NGINX randomly selects two candidate servers, then picks the one with fewer active connections (weighted by server weights). This simple strategy dramatically reduces load imbalance compared to pure random selection.

**When to use Power of Two Choices:**

- Large server pools where tracking all connections is expensive
- Environments where servers have varying capacities
- As a simpler alternative to least connections with similar results

### Beyond Built-in Algorithms: NGINX Plus and Angie

The algorithms above are available in open-source NGINX. Two notable extensions exist:

- **NGINX Plus** adds the `least_time` directive, which routes traffic based on measured response latency and active connections. This is the most sophisticated built-in option but requires a commercial subscription.
- **Angie** (an NGINX fork) has ported the `sticky` session persistence directive from NGINX Plus to open source, but has not added `least_time`.

For load-aware balancing without NGINX Plus, the **fair** third-party module (covered below) tracks active requests in shared memory across all workers. See the dedicated guide on NGINX fair load balancing for a complete comparison and configuration reference.

## Server Parameters

Each server in an upstream block accepts parameters that control its behavior.

### weight

Specifies the relative capacity of a server. Default is 1.

```
server 192.168.1.10:8080 weight=5;
```

### max\_conns

Limits the maximum number of simultaneous connections to a server. When the limit is reached, requests queue or fail over to other servers.

```
server 192.168.1.10:8080 max_conns=100;
```

This prevents overwhelming a server during traffic spikes. Set based on your server’s capacity and application requirements.

### max\_fails and fail\_timeout

These parameters control passive health checking.

```
server 192.168.1.10:8080 max_fails=3 fail_timeout=30s;
```

- `max_fails` – Number of failed attempts before marking server unavailable (default: 1)
- `fail_timeout` – Time period for counting failures and duration of unavailability (default: 10s)

When a server fails `max_fails` times within `fail_timeout`, NGINX marks it unavailable for the remaining `fail_timeout` period. After that, NGINX tries again.

### backup

Designates a server as backup. NGINX only uses backup servers when all primary servers are unavailable.

```
upstream backend {
    server 192.168.1.10:8080;
    server 192.168.1.11:8080;
    server 192.168.1.12:8080 backup;
}
```

### down

Permanently marks a server as unavailable. Use this for maintenance.

```
server 192.168.1.10:8080 down;
```

## Connection Keepalive Optimization

By default, NGINX opens a new connection to the backend for each client request. For high-traffic sites, this creates significant overhead. Connection keepalive maintains persistent connections to backends.

```
upstream backend {
    server 192.168.1.10:8080;
    server 192.168.1.11:8080;
    server 192.168.1.12:8080;
    keepalive 32;
}
```

**Critical configuration for HTTP/1.1 backends:**

```
location /api/ {
    proxy_pass <http://backend>;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
}
```

Without `proxy_http_version 1.1` and clearing the `Connection` header, keepalive won’t work. NGINX defaults to HTTP/1.0 for upstream connections, which closes connections after each response.

**Additional keepalive parameters:**

```
upstream backend {
    server 192.168.1.10:8080;
    server 192.168.1.11:8080;
    keepalive 32;
    keepalive_requests 1000;
    keepalive_timeout 60s;
}
```

- `keepalive 32` – Maximum idle connections per worker process
- `keepalive_requests 1000` – Maximum requests per connection before closing
- `keepalive_timeout 60s` – Idle timeout for keepalive connections

For more performance tuning, see our guide on tuning worker\_rlimit\_nofile in NGINX and worker\_processes.

## Health Checks and Failover

NGINX provides multiple mechanisms for handling server failures.

### Passive Health Checks

Configure with `max_fails` and `fail_timeout`:

```
upstream backend {
    server 192.168.1.10:8080 max_fails=3 fail_timeout=30s;
    server 192.168.1.11:8080 max_fails=3 fail_timeout=30s;
    server 192.168.1.12:8080 max_fails=3 fail_timeout=30s;
}
```

### Request Failover

The `proxy_next_upstream` directive controls when NGINX retries a request on another server:

```
location /api/ {
    proxy_pass <http://backend>;
    proxy_next_upstream error timeout http_500 http_502 http_503 http_504;
    proxy_next_upstream_tries 3;
    proxy_next_upstream_timeout 10s;
}
```

- `proxy_next_upstream` – Conditions that trigger failover
- `proxy_next_upstream_tries` – Maximum retry attempts
- `proxy_next_upstream_timeout` – Total time limit for retries

**Available conditions:**

- `error` – Connection error or no response
- `timeout` – Connection timeout or response timeout
- `invalid_header` – Invalid response from server
- `http_500`, `http_502`, `http_503`, `http_504` – Specific HTTP errors
- `http_403`, `http_404`, `http_429` – Additional HTTP error codes
- `non_idempotent` – Allow retrying POST/PATCH/DELETE (disabled by default)
- `off` – Disable failover entirely

### Connection Timeouts

Configure appropriate timeouts for your application:

```
location /api/ {
    proxy_pass <http://backend>;
    proxy_connect_timeout 10s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
}
```

## Shared Memory Zones

For NGINX Plus or when using certain third-party modules, shared memory zones enable runtime state sharing across worker processes:

```
upstream backend {
    zone backend_zone 64k;
    server 192.168.1.10:8080;
    server 192.168.1.11:8080;
    server 192.168.1.12:8080;
}
```

The `zone` directive allocates shared memory for:

- Connection counts accurate across all workers
- Health check state
- Runtime configuration changes (NGINX Plus)

The size (`64k` in this example) should accommodate your server count. Each server entry requires approximately 1KB.

## Advanced Modules for Load Balancing

The standard NGINX package covers most use cases, but third-party modules extend load balancing capabilities significantly. These modules are available as pre-built packages for RHEL-based distributions.

### Sticky Cookie Session Persistence

The `ip_hash` directive has a major limitation: clients behind NAT or corporate proxies share the same IP address, causing uneven distribution. The sticky module solves this by using cookies for session persistence.

Install the module:

```
dnf install -y <https://extras.getpagespeed.com/release-latest.rpm>
dnf install -y nginx-module-sticky
```

Enable it in `/etc/nginx/nginx.conf`:

```
load_module modules/ngx_http_sticky_module.so;
```

Configure sticky sessions:

```
upstream backend {
    sticky name=route expires=1h domain=.example.com path=/ httponly secure;
    server 192.168.1.10:8080;
    server 192.168.1.11:8080;
    server 192.168.1.12:8080;
}
```

For enhanced security, use HMAC-signed cookies:

```
upstream backend {
    sticky hmac=sha1 hmac_key=your_secret_key name=route;
    server 192.168.1.10:8080;
    server 192.168.1.11:8080;
}
```

**When to use sticky cookies:**

- Applications with server-side sessions behind load balancers
- Environments where clients share IP addresses (corporate networks, mobile carriers)
- When you need cryptographically secure session affinity

For a complete guide, see NGINX sticky sessions.

### Fair Load Balancer

The fair module tracks the number of active in-flight requests per backend in a shared memory zone across all NGINX worker processes. This gives it a global view of server busyness — unlike `least_conn`, which only sees connections within each individual worker. When a new request arrives, it is routed to the backend with the fewest active requests, automatically directing more traffic to faster servers.

Install and enable:

```
dnf install -y nginx-module-upstream-fair

load_module modules/ngx_http_upstream_fair_module.so;
```

Configure fair balancing:

```
upstream backend {
    fair;
    server 192.168.1.10:8080;
    server 192.168.1.11:8080;
    server 192.168.1.12:8080;
}
```

The module also supports optional parameters like `weight_mode=peak` (caps concurrency per backend at its weight value) and `weight_mode=idle` (prioritizes completely idle backends).

**When to use fair balancing:**

- Heterogeneous backend environments with varying performance characteristics
- Applications where backend response times fluctuate significantly
- Deployments with multiple NGINX worker processes that need accurate cross-worker load tracking
- As an open-source alternative to the NGINX Plus `least_time` directive

For detailed configuration, advanced examples, and a comparison with NGINX Plus and Angie, see the dedicated NGINX fair load balancing guide.

### Dynamic DNS Resolution

Standard NGINX resolves upstream hostnames only at startup or reload. If a backend IP changes — common in cloud, container, and auto-scaling environments — NGINX keeps routing to the stale address until you manually reload.

**NGINX 1.28+ (recommended):** The native `resolve` parameter on the `server` directive solves this problem directly. It re-resolves domain names in the background based on DNS TTL, with no third-party module needed:

```
upstream backend {
    zone backend_zone 64k;
    resolver 8.8.8.8 valid=30s;
    server api.example.com:8080 resolve;
}
```

For the full guide on native DNS resolution — including comparison with Angie (which shipped this feature in open source since January 2023) and NGINX Plus — see NGINX Upstream Resolve: Dynamic DNS for Load Balancing.

**Older NGINX versions (pre-1.27.3):** If you cannot upgrade to NGINX 1.28+, the jdomain module provides request-driven DNS re-resolution as a third-party dynamic module:

```
dnf install -y nginx-module-upstream-jdomain

load_module modules/ngx_http_upstream_jdomain_module.so;

resolver 8.8.8.8;

upstream backend {
    jdomain api.example.com port=8080 max_ips=10 interval=10;
}
```

For auto-scaling environments with failback:

```
upstream backend {
    server 127.0.0.2 backup;
    jdomain backend.internal.example.com port=8080 strict;
}
```

For the complete jdomain directive reference, comparison with native `resolve`, and migration instructions, see NGINX Upstream Jdomain: Dynamic DNS for Any NGINX Version.

**When to use dynamic DNS:**

- Kubernetes or container orchestration platforms
- Auto-scaling groups in cloud environments
- Any scenario where backend IPs change without NGINX reload

### Dynamic Upstream via Service Discovery (Consul/etcd)

DNS-based re-resolution handles IP address changes, but it cannot add or remove entirely new servers at runtime. In microservices environments where backends register and deregister from a service registry like Consul or etcd, you need a deeper integration.

The upsync module polls Consul or etcd at configurable intervals and updates the upstream server list in memory — without any NGINX reload. Servers are added, removed, or reconfigured (weight, max\_fails, fail\_timeout) entirely at runtime. A local dump file provides disaster recovery if the service registry becomes unavailable.

Install and enable:

```
dnf install -y nginx-module-upsync

load_module modules/ngx_http_upsync_module.so;
```

Configure with Consul:

```
upstream backend {
    upsync 127.0.0.1:8500/v1/kv/upstreams/backend upsync_timeout=6m upsync_interval=500ms upsync_type=consul strong_dependency=off;
    upsync_dump_path /etc/nginx/upsync/backend_dump.conf;
    upsync_lb least_conn;

    include /etc/nginx/upsync/backend_dump.conf;
}
```

The module supports Consul (KV store, service catalog, and health API) and etcd. A companion stream module (`nginx-module-stream-upsync`) provides the same functionality for TCP/UDP load balancing.

**When to use upsync:**

- Microservices with Consul or etcd service registration
- Environments requiring zero-reload backend changes
- When native DNS `resolve` is insufficient because servers are not in the config file

For the complete configuration reference, comparison with NGINX Plus API and Angie, and production deployment guide, see NGINX Dynamic Upstream: Consul and etcd Upsync Guide.

## Production Configuration Example

Here’s a complete production-ready NGINX load balancing configuration:

```
upstream backend_api {
    least_conn;
    zone backend_api 64k;

    server 192.168.1.10:8080 weight=5 max_fails=3 fail_timeout=30s max_conns=100;
    server 192.168.1.11:8080 weight=3 max_fails=3 fail_timeout=30s max_conns=100;
    server 192.168.1.12:8080 weight=2 max_fails=3 fail_timeout=30s max_conns=100;
    server 192.168.1.13:8080 backup;

    keepalive 32;
    keepalive_requests 1000;
    keepalive_timeout 60s;
}

server {
    listen 80;
    server_name api.example.com;

    location / {
        proxy_pass http://backend_api;

        # HTTP/1.1 for keepalive
        proxy_http_version 1.1;
        proxy_set_header Connection "";

        # Proper headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 10s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # Failover
        proxy_next_upstream error timeout http_500 http_502 http_503 http_504;
        proxy_next_upstream_tries 3;
        proxy_next_upstream_timeout 10s;

        # Buffering
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 16k;
        proxy_busy_buffers_size 32k;
    }
}
```

For more on proxy buffer configuration, see tuning proxy\_buffer\_size in NGINX.

Test the configuration before applying:

```
nginx -t
```

Reload NGINX to apply changes:

```
systemctl reload nginx
```

## TCP/UDP Load Balancing with Stream Module

NGINX can also load balance TCP and UDP traffic using the stream module:

```
stream {
    upstream mysql_backend {
        least_conn;
        server 192.168.1.10:3306 max_fails=3 fail_timeout=30s;
        server 192.168.1.11:3306 max_fails=3 fail_timeout=30s;
        server 192.168.1.12:3306 backup;
    }

    server {
        listen 3306;
        proxy_pass mysql_backend;
        proxy_connect_timeout 10s;
        proxy_timeout 300s;
    }
}
```

The stream block typically goes in `/etc/nginx/nginx.conf` or a file included from there.

## Monitoring Load Balancer Performance

Monitor your load balancer using NGINX’s stub status module:

```
server {
    listen 127.0.0.1:8080;

    location /nginx_status {
        stub_status;
        allow 127.0.0.1;
        deny all;
    }
}
```

Access the status page:

```
curl <http://127.0.0.1:8080/nginx_status>
```

This shows active connections, requests per second, and connection states.

For detailed upstream metrics, consider NGINX Plus or compatible monitoring solutions that parse NGINX logs.

## Troubleshooting Common Issues

### All Servers Marked as Unavailable

If all upstream servers fail health checks, NGINX returns 502 Bad Gateway. Check:

1. Backend server accessibility from the NGINX host
2. Firewall rules allowing traffic on backend ports
3. Backend application health

### Uneven Load Distribution

With round-robin, verify all servers are actually receiving traffic:

1. Check server weights
2. Ensure keepalive connections aren’t causing stickiness
3. Verify all servers pass health checks

### Connection Timeouts

If clients see timeouts:

1. Check `proxy_connect_timeout` for connection establishment
2. Verify `proxy_read_timeout` is sufficient for your slowest endpoints
3. Monitor backend server response times

### Session Persistence Issues

If users lose sessions when switching servers:

1. Use IP hash or consistent hash for session stickiness
2. Implement shared session storage (Redis, Memcached)
3. Consider JWT tokens for stateless authentication

## Summary

NGINX load balancing provides flexible, high-performance traffic distribution. Choose your algorithm based on your application’s needs:

- **Round-robin** for stateless applications with similar server capacity
- **Least connections** for requests with variable processing times
- **IP hash** for simple session persistence
- **Consistent hash** when minimizing redistribution during scaling matters
- **Random with Power of Two Choices** for large server pools
- **Sticky cookies** for reliable session affinity behind NAT
- **Fair balancing** for load-aware distribution across heterogeneous backends
- **Upsync** for dynamic service discovery with Consul or etcd

Always configure proper health checks, connection keepalive, and failover behavior for production deployments. Test your configuration thoroughly before applying changes to live systems.

For more information, explore the official NGINX load balancing documentation.

**Upstream config moves faster than security review.** Continuous scanning catches the lag between an upstream change and the next manual audit. **GetPageSpeed Amplify** runs scheduled gixy scans across every host and ties findings to live NGINX runtime metrics. Drop-in compatible with the deprecated `nginx-amplify-agent` (EOL January 2026).