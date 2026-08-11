"""Full DNS lookup tool.

Forward lookups across the common record types (A, AAAA, CNAME, MX, NS,
TXT, SOA) for a hostname, and a reverse (PTR) lookup for an IP address -
the shape of the input decides which one runs.

Unlike Connection.ping (backed by the Ping model), results here are not
persisted: a lookup tool answers "what do these records say right now",
not "how has this changed over time", so there's no reporting need that
would justify a table - same reasoning as the stateless checks in
Connection.services.
"""

import ipaddress

import dns.exception
import dns.resolver
import dns.reversename

FORWARD_RECORD_TYPES = ["A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA"]

# A lookup here is one user click waiting on a page load, not a
# background poll - a query that's genuinely stuck should fail fast
# rather than hang the request.
QUERY_TIMEOUT = 3  # per single try, seconds
QUERY_LIFETIME = 5  # total budget across retries, seconds


def _resolver():
    resolver = dns.resolver.Resolver()
    resolver.timeout = QUERY_TIMEOUT
    resolver.lifetime = QUERY_LIFETIME
    return resolver


def is_ip_address(value):
    try:
        ipaddress.ip_address(value.strip())
        return True
    except ValueError:
        return False


def forward_lookup(hostname, record_types=None):
    """Query every type in `record_types` (default: FORWARD_RECORD_TYPES)
    for `hostname`.

    Returns {"hostname", "exists", "error", "results": [...]}. If the
    domain itself doesn't exist (NXDOMAIN on any type), `exists` is
    False and the remaining types are skipped - querying six more types
    for a domain that doesn't exist would just be six more identical
    failures. A domain that exists but simply has no record of a given
    type (NoAnswer, e.g. no CNAME at an apex) is a normal outcome, not
    an error, and is reported per-type as found=False, error=None.
    """
    record_types = record_types or FORWARD_RECORD_TYPES
    resolver = _resolver()

    results = []
    for record_type in record_types:
        try:
            answer = resolver.resolve(hostname, record_type)
        except dns.resolver.NXDOMAIN:
            return {
                "hostname": hostname,
                "exists": False,
                "error": "دامنه یافت نشد (NXDOMAIN)",
                "results": [],
            }
        except dns.resolver.NoAnswer:
            results.append(
                {"record_type": record_type, "found": False, "error": None, "records": [], "ttl": None}
            )
            continue
        except dns.exception.DNSException as exc:
            results.append(
                {"record_type": record_type, "found": False, "error": str(exc), "records": [], "ttl": None}
            )
            continue

        results.append(
            {
                "record_type": record_type,
                "found": True,
                "error": None,
                "records": [rdata.to_text() for rdata in answer],
                "ttl": answer.rrset.ttl,
            }
        )

    return {"hostname": hostname, "exists": True, "error": None, "results": results}


def reverse_lookup(ip_address):
    """PTR lookup for an IPv4 or IPv6 address."""
    resolver = _resolver()
    try:
        rev_name = dns.reversename.from_address(ip_address)
        answer = resolver.resolve(rev_name, "PTR")
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return {"ip_address": ip_address, "found": False, "error": None, "hostnames": []}
    except dns.exception.DNSException as exc:
        return {"ip_address": ip_address, "found": False, "error": str(exc), "hostnames": []}

    return {
        "ip_address": ip_address,
        "found": True,
        "error": None,
        "hostnames": [rdata.to_text() for rdata in answer],
    }


def lookup(query):
    """Single entry point: detect whether `query` is an IP address or a
    hostname and dispatch to the matching lookup."""
    query = query.strip()
    if is_ip_address(query):
        return {"kind": "reverse", "query": query, "result": reverse_lookup(query)}
    return {"kind": "forward", "query": query, "result": forward_lookup(query)}
