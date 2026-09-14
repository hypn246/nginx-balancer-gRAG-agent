# HTTP Load Balancing

Type of document: How-to guide
Product: NGINX Plus
> Load balance HTTP traffic across web or application server groups, with several algorithms and advanced features like slow-start and session persistence.

## Overview {#overview}
Load balancing across multiple application instances is a common technique for optimizing resource utilization, maximizing throughput, reducing latency, and improving fault‑tolerance.

NGINX and NGINX Plus provide Layer 7 (application layer) load balancing for HTTP and HTTPS traffic. You can choose from multiple load-balancing algorithms, ranging from basic Round Robin to more advanced methods such as Least Connections, Least Time, and hashing-based methods. NGINX Plus adds more capabilities such as slow-start, which gracefully reintroduces recovered servers, and session persistence (“sticky” sessions) which routes a client’s requests to the same upstream server.
.

## Proxy HTTP traffic to a group of servers {#proxy_pass}

Use NGINX or NGINX Plus to load balance across a group of servers. First, define the group of servers with the upstream directive. Place the directive in the httpcontext.

Servers in the group are configured using the `server` directive (not to be confused with the `server` block that defines a virtual server running on NGINX). For example, the following configuration defines a group named **backend** and consists of three server configurations. This may resolve to more than three actual servers:

```nginx
http {
    upstream backend {
        server backend1.example.com weight=5;
        server backend2.example.com;
        server 192.0.0.1 backup;
    }
}
```

To pass requests to a server group, the name of the group is specified in the `proxy_pass` directive. If using an alternate protocol such as fastcgi, use that protocol's pass directive instead. The list of alternate pass directives is: `fastcgi_pass`, `memcached_pass`, `scgi_pass`, `uwsgi_pass`.

In the next example, a virtual server running on NGINX passes all requests to the **backend** upstream group defined in the previous example:

```nginx
server {
    location / {
        proxy_pass http://backend;
    }
}
```

The following example combines the two snippets above and shows how to proxy HTTP requests to the **backend** server group. The group consists of three servers, two of them running instances of the same application while the third is a backup server.

```nginx
http {
    upstream backend {
        server backend1.example.com;
        server backend2.example.com;
        server 192.0.0.1 backup;
    }

    server {
        location / {
            proxy_pass http://backend;
        }
    }
}
```

## **Choose a load balancing method {#method}**

NGINX Open Source supports five load balancing methods: Round Robin, Least Connections, Least Time, IP Hash, and Generic Hash.
NGINX Plus supports six load balancing methods: all of the above, plus Random.

> **Note:** When configuring any method other than Round Robin, put the corresponding directive `hash`, `ip_hash`, `least_conn`, `least_time`, or `random` above the list of `server` directives in the `upstream {}` block.

1. "Round Robin" – Requests are distributed evenly across the servers, with [server weights](#weights) taken into consideration. This method is used by default; there is no directive for enabling it.

    ```nginx
    upstream backend {
       # no load balancing method is specified for Round Robin
       server backend1.example.com;
       server backend2.example.com;
    }
    ```

2. "Least Connections" – A request is sent to the server with the least number of active connections. This method also takes  [server weights](#weights) into consideration.

    ```nginx
    upstream backend {
        least_conn;
        server backend1.example.com;
        server backend2.example.com;
    }
    ```

3. "IP Hash" – The server to which a request is sent is determined from the client IP address. In this case, either the first three octets of the IPv4 address or the whole IPv6 address is used to calculate the hash value. The method guarantees that requests from the same address get to the same server unless it is not available.

    ```nginx
    upstream backend {
        ip_hash;
        server backend1.example.com;
        server backend2.example.com;
    }
    ```

    If one of the servers needs to be temporarily removed from the load‑balancing rotation, it can be marked with the `down` parameter. This preserves the current hashing of client IP addresses. Requests that were to be processed by this server are automatically sent to the next server in the group.

    ```nginx
    upstream backend {
        server backend1.example.com;
        server backend2.example.com;
        server backend3.example.com down;
    }
    ```

4. "Generic Hash" – The server to which a request is sent is determined from a user‑defined key. This key can be a text string, a variable, or a combination. For example, the key may be a paired source IP address and port. This example uses a URI:

    ```nginx
    upstream backend {
        hash $request_uri consistent;
        server backend1.example.com;
        server backend2.example.com;
    }
    ```

    The optional `consistent` parameter to the `hash` directive enables `ketama ` consistent‑hash load balancing. Requests are evenly distributed across all upstream servers based on the user‑defined hashed key value. If an upstream server is added to or removed from an upstream group, only a few keys are remapped, which minimizes cache misses. This is useful for load balancing cache servers or other applications that accumulate state.

5. "Least Time" – For each request, NGINX selects the server with the lowest average latency and the lowest number of active connections. The lowest average latency is calculated based the `parameter` included with the `least_time` directive. This parameter can be one of the following:

    - `header` – Time to receive the first byte from the server
    - `last_byte` – Time to receive the full response from the server
    - `last_byte inflight` – Time to receive the full response from the server, taking into account incomplete requests

    ```nginx
    upstream backend {
        least_time header;
        server backend1.example.com;
        server backend2.example.com;
    }
    ```

6. "Random" (NGINX Plus only) – Each request will be passed to a randomly selected server. This method takes into account server weights.
If the `two` parameter is specified, NGINX first randomly selects two servers, then chooses between these servers using one of the following specified methods:

    - `least_conn` – The least number of active connections
    - `least_time=header` (NGINX Plus) – The least average time to receive the response header from the server ([`$upstream_header_time`](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#var_upstream_header_time))
    - `least_time=last_byte` (NGINX Plus) – The least average time to receive the full response from the server ([`$upstream_response_time`](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#var_upstream_response_time))

    ```nginx
    upstream backend {
        random two least_time=last_byte;
        server backend1.example.com;
        server backend2.example.com;
        server backend3.example.com;
        server backend4.example.com;
    }
    ```

    The **Random** load balancing method should be used for distributed environments where multiple load balancers are passing requests to the same set of backends. For environments where the load balancer has a full view of all requests, use other load balancing methods.

## Server weights {#weights}

Some load balancing methods, including Round Robin, Least Connections, and Random, distribute requests according to their server weights. The `weight` parameter to the `server` directive sets the weight of a server. If no weight is set, it defaults to `1`:

```nginx
upstream backend {
    server backend1.example.com weight=5;
    server backend2.example.com;
    server 192.0.0.1 backup;
}
```

In the example above, **backend1.example.com** has weight `5`, while the other two servers have the default weight (`1`). However, the one with IP address `192.0.0.1` is marked as a `backup` server and does not receive requests unless both of the other servers are unavailable. With this configuration of weights, out of every `6` requests, `5` are sent to **backend1.example.com** and `1` to **backend2.example.com**.

## Server slow-start {#slow_start}

The server slow‑start feature prevents a recently recovered server from being overwhelmed by connections, which may time out and cause the server to be marked as failed again. This feature is only available in NGINX Plus.

Slow‑start allows an upstream server to gradually recover its weight from `0` to its nominal value after it has recovered or become available. This can be done with the `slow_start` parameter to the `server` directive:

```nginx
upstream backend {
    server backend1.example.com slow_start=30s;
    server backend2.example.com;
    server 192.0.0.1 backup;
}
```

The time value (here, `30` seconds) sets the time during which NGINX Plus ramps up the number of connections to the server to the full value. If no value is specified, it defaults to `0`, which disables slow-start.

> **Note:** If there is only a single server in a group, the `max_fails`, `fail_timeout`, and `slow_start` parameters to the `server` directive are ignored, and the server is never considered unavailable.

## Session persistence {#sticky}

Session persistence means that NGINX Plus identifies user sessions and routes all requests in a given session to the same upstream server.

NGINX Plus supports three session persistence methods. The methods are set with the `sticky` directive. (For session persistence with NGINX Open Source, use the `hash` or `ip_hash` directive as described above.)

- "Sticky cookie" – NGINX Plus adds a session cookie to the first response from the upstream group and identifies the server that sent the response. The client's next request contains the cookie value, and NGINX Plus routes the request to the upstream server that responded to the first request. This is the simplest session persistence method.

    ```nginx
    upstream backend {
        server backend1.example.com;
        server backend2.example.com;
        sticky cookie srv_id expires=1h domain=.example.com path=/;
    }
    ```

    In the example above, the `srv_id` parameter sets the name of the cookie. The optional `expires` parameter sets the time for the browser to keep the cookie (here, `1` hour). The optional `domain` parameter defines the domain for which the cookie is set, and the optional `path` parameter defines the path for which the cookie is set.

- "Sticky route"– Use the `route` parameter to the `server` directive to assign a route identifier to each server. NGINX Plus assigns one of the route identifiers to the client when it receives the client's first request. Subsequent requests then compare these route identifiers, which are either stored in a cookie or passed in the request URI.

    ```nginx
    upstream backend {
        server backend1.example.com route=a;
        server backend2.example.com route=b;
        sticky route $route_cookie $route_uri;
    }
    ```
    In the example above, the session cookie is checked first for the route identifier. If there is none, then the URI is checked second.

- "Sticky learn" – NGINX Plus first finds session identifiers by inspecting requests and responses. Then NGINX Plus “learns” which upstream server corresponds to which session identifier. Generally, these identifiers are passed in a HTTP cookie. If a request contains a session identifier already “learned”, NGINX Plus forwards the request to the corresponding server:

    ```nginx
    upstream backend {
       server backend1.example.com;
       server backend2.example.com;
       sticky learn
           create=$upstream_cookie_examplecookie
           lookup=$cookie_examplecookie
           zone=client_sessions:1m
           timeout=1h;
    }
    ```

    In the example, one of the upstream servers creates a session by setting the cookie `EXAMPLECOOKIE` in the response.

    The mandatory `create` parameter specifies a variable that indicates how a new session is created. In the example, new sessions are created from the cookie `EXAMPLECOOKIE` sent by the upstream server.

    The mandatory `lookup` parameter specifies how to search for existing sessions. In our example, existing sessions are searched in the cookie `EXAMPLECOOKIE` sent by the client.

    The mandatory `zone` parameter specifies a shared memory zone where all information about sticky sessions is kept. In our example, the zone is named **client_sessions** and is `1` megabyte in size.

    This is a more sophisticated session persistence method than the previous two as it does not require keeping any cookies on the client side: all info is kept server‑side in the shared memory zone.

    If there are several NGINX instances in a cluster that use the "sticky learn" method, it is possible to sync the contents of their shared memory zones on conditions that:
  - the zones have the same name
  - the `zone_sync`functionality is configured on each instance
  - the `sync` parameter is specified

    ```nginx
       sticky learn
           create=$upstream_cookie_examplecookie
           lookup=$cookie_examplecookie
           zone=client_sessions:1m
           timeout=1h
           sync;
    ```

    See [Runtime State Sharing in a Cluster](nginx/admin-guide/high-availability/zone_sync.md) for details.

## Limit the number of connections {#maxconns}

With NGINX Plus, it is possible to limit the number of active connections to an upstream server.

The `max_conns` parameter sets the maximum number of connections to the upstream server.

The `queue` directive allows excess connections to be held in a queue. It requires a maximum number for the queue and a timeout.

If the `max_conns` limit has been reached, the request is placed in a queue for further processing. If the queue limit has been reached, if no queue directive is specified, or if a client reaches the `timeout` time in queue, the client will receive an error.

```nginx
upstream backend {
    server backend1.example.com max_conns=3;
    server backend2.example.com;
    queue 100 timeout=70;
}
```

> **Note:** The `max_conns` limit is ignored if there are idle `keepalive` connections opened in other `worker processes`. As a result, the total number of connections to the server might exceed the `max_conns` value in a configuration where the memory is [shared with multiple worker processes](#zone).

## Configure health checks {#health}

NGINX can continually test your HTTP upstream servers, avoid the servers that have failed, and gracefully add the recovered servers into the load‑balanced group.

See [HTTP Health Checks](nginx/admin-guide/load-balancer/http-health-check.md) for instructions how to configure health checks for HTTP.

## Share data with multiple worker processes {#zone}

If an `upstream` block does not include the `zone` directive, each worker process keeps its own copy of the server group configuration and maintains its own set of related counters. The counters include the current number of connections to each server in the group and the number of failed attempts to pass a request to a server. As a result, the server group configuration cannot be modified dynamically.

When the `zone` directive is included in an `upstream` block, the configuration of the upstream group is kept in a memory area shared among all worker processes. This scenario is dynamically configurable, because the worker processes access the same copy of the group configuration and utilize the same related counters.

The `zone` directive is mandatory for [active health checks] and [dynamic reconfiguration] of the upstream group. However, other features of upstream groups can benefit from the use of this directive as well.

For example, if the configuration of a group is not shared, each worker process maintains its own counter for failed attempts to pass a request to a server (set by the `max_fails` parameter). In this case, each request gets to only one worker process. When the worker process that is selected to process a request fails to transmit the request to a server, other worker processes don’t know anything about it. While some worker process can consider a server unavailable, others might still send requests to this server. For a server to be definitively considered unavailable, the number of failed attempts during the timeframe set by the `fail_timeout` parameter must equal `max_fails` multiplied by the number of worker processes. On the other hand, the `zone` directive guarantees the expected behavior.

Similarly, the Least Connections load‑balancing method might not work as expected without the `zone` directive, at least under low load. This method passes a request to the server with the smallest number of active connections. If the configuration of the group is not shared, each worker process uses its own counter for the number of connections and might send a request to the same server that another worker process just sent a request to.  However, you can increase the number of requests to reduce this effect. Under high load requests are distributed among worker processes evenly, and the `Least Connections` method works as expected.

### Set the zone size {#zone-size}

It is not possible to recommend an ideal memory‑zone size, because usage patterns vary widely. The required amount of memory is determined by which features (such as [session persistence](#sticky), [health checks](#health_active), or [DNS re‑resolving](#resolve)) are enabled and how the upstream servers are identified.

As an example, with the `sticky_route` session persistence method and a single health check enabled, a 256‑KB zone can accommodate information about the indicated number of upstream servers:

- 128 servers (each defined as an IP‑address:port pair)
- 88 servers (each defined as hostname:port pair where the hostname resolves to a single IP address)
- 12 servers (each defined as hostname:port pair where the hostname resolves to multiple IP addresses)

