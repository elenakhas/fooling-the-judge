"""Minimal provider-agnostic chat call (Anthropic native or any OpenAI-compatible endpoint)."""
import json, os, time, urllib.request, urllib.error


def call(provider, base_url, model, key, system, user, temperature=0.0, max_tokens=600, return_usage=False):
    """user: a string (single turn) or a list of {"role": "user"|"assistant", "content": str}."""
    turns = [{"role": "user", "content": user}] if isinstance(user, str) else list(user)
    if provider == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        body = {"model": model, "max_tokens": max_tokens, "messages": turns}
        if temperature is not None:          # thinking models may reject temperature: pass None to omit
            body["temperature"] = temperature
        if system:
            body["system"] = system
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    else:
        url = base_url.rstrip("/") + "/chat/completions"
        msgs = ([{"role": "system", "content": system}] if system else []) + turns
        body = {"model": model, "max_tokens": max_tokens, "messages": msgs}
        if temperature is not None:
            body["temperature"] = temperature
        # extra request fields for OpenAI-compatible routers, e.g. OpenRouter provider pinning:
        # LLM_EXTRA_BODY='{"provider": {"order": ["deepinfra"], "allow_fallbacks": false}}'
        if os.environ.get("LLM_EXTRA_BODY"):
            body.update(json.loads(os.environ["LLM_EXTRA_BODY"]))
        headers = {"Authorization": f"Bearer {key}", "content-type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                out = json.loads(r.read())
            usage = out.get("usage") or {}
            if provider == "anthropic":
                text = "".join(b.get("text", "") for b in out.get("content", []) if b.get("type", "text") == "text")
            else:
                text = out["choices"][0]["message"].get("content") or ""
                # record who actually served the request (OpenRouter returns the provider; routers may swap models)
                usage = dict(usage, served_by=out.get("provider"), served_model=out.get("model"))
            return (text, usage) if return_usage else text
        except urllib.error.HTTPError as e:
            if e.code == 400 and "temperature" in body and attempt < 4:
                detail = e.read().decode("utf-8", "replace")
                if "temperature" in detail:          # model rejects temperature: retry once without it
                    body.pop("temperature")
                    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
                    continue
                raise RuntimeError(f"HTTP 400: {detail[:300]}")
            if e.code in (429, 500, 502, 503, 529) and attempt < 4:
                time.sleep(2 ** attempt * 3)
                continue
            raise RuntimeError(f"HTTP {e.code}: {e.read()[:300]}")
        except urllib.error.URLError:
            if attempt < 4:
                time.sleep(2 ** attempt * 3)
                continue
            raise


def get_key(provider, key_env=None):
    name = key_env or ("ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY")
    return os.environ.get(name)


def fill(template, item):
    fields = {k: ("" if v is None else v) for k, v in item.items()}
    fields.setdefault("mode", item.get("pressure_mode", ""))
    for k in ("obscure_context", "honest_alt", "t1", "s2"):
        fields.setdefault(k, "")
    return template.format(**fields)


# ---------------------------------------------------------------------------------------------
# Message Batches API (Anthropic): 50% price, asynchronous (most batches finish within an hour, at most 24 h).
# ---------------------------------------------------------------------------------------------
BATCH_URL = "https://api.anthropic.com/v1/messages/batches"


def _http(method, url, key, body=None):
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 529) and attempt < 4:
                time.sleep(2 ** attempt * 3); continue
            raise RuntimeError(f"HTTP {e.code}: {e.read()[:300]}")
        except urllib.error.URLError:
            if attempt < 4:
                time.sleep(2 ** attempt * 3); continue
            raise


def batch_params(model, system, user, temperature, max_tokens):
    """Same request body as call() for the Anthropic provider."""
    body = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": user}]}
    if temperature is not None:
        body["temperature"] = temperature
    if system:
        body["system"] = system
    return body


def batch_submit(key, requests):
    """requests: [{"custom_id": str, "params": {...}}] -> batch id."""
    return json.loads(_http("POST", BATCH_URL, key, {"requests": requests}))["id"]


def batch_status(key, batch_id):
    return json.loads(_http("GET", f"{BATCH_URL}/{batch_id}", key))


def batch_results(key, status):
    """Yield (custom_id, text or None, usage, error) for an ended batch."""
    raw = _http("GET", status["results_url"], key).decode("utf-8")
    for line in raw.splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        res = r.get("result") or {}
        if res.get("type") == "succeeded":
            m = res["message"]
            text = "".join(b.get("text", "") for b in m.get("content", []) if b.get("type", "text") == "text")
            yield r["custom_id"], text, m.get("usage") or {}, None
        else:
            yield r["custom_id"], None, {}, json.dumps(res)[:300]


# ---------------------------------------------------------------------------------------------
# OpenRouter Batch API (OpenAI-compatible bodies; about half price, results within 24 h, up to 5,000 requests/batch).
# Same interface as the Anthropic helpers above: submit -> id; status -> {"processing_status": "ended"|..., ...};
# results -> (custom_id, text, usage, error).
# ---------------------------------------------------------------------------------------------
def _or_http(method, url, key, body=None):
    headers = {"Authorization": f"Bearer {key}", "content-type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None    # dict order kept: requests must come last
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 4:
                time.sleep(2 ** attempt * 3); continue
            raise RuntimeError(f"HTTP {e.code}: {e.read()[:400]}")
        except urllib.error.URLError:
            if attempt < 4:
                time.sleep(2 ** attempt * 3); continue
            raise


def or_batch_body(system, user, temperature, max_tokens, extra=None):
    """Per-request body (OpenAI chat shape). 'provider' is NOT allowed here (it would not pin): pass it to submit."""
    body = {"messages": ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}],
            "max_tokens": max_tokens}
    if temperature is not None:
        body["temperature"] = temperature
    body.update({k: v for k, v in (extra or {}).items() if k != "provider"})
    return body


def or_batch_submit(key, base_url, model, requests, provider=None):
    """requests: [{"custom_id": str, "body": {...}}]. provider (e.g. {"order": [...], "allow_fallbacks": False}) pins the batch."""
    body = {"endpoint": "/v1/chat/completions", "model": model}
    if provider:
        body["provider"] = provider
    body["requests"] = requests
    return _or_http("POST", base_url.rstrip("/") + "/batches", key, body)["id"]


OR_FINAL = {"completed", "failed", "expired", "cancelled"}


def or_batch_status(key, base_url, batch_id):
    st = _or_http("GET", f"{base_url.rstrip('/')}/batches/{batch_id}", key)
    st["processing_status"] = "ended" if st.get("status") in OR_FINAL else st.get("status", "?")
    rc = st.get("request_counts") or {}
    st["request_counts"] = {"succeeded": rc.get("completed", 0), "processing": max(0, rc.get("total", 0) - rc.get("completed", 0) - rc.get("failed", 0))}
    return st


def or_batch_results(key, status):
    if status.get("status") != "completed":
        err = json.dumps(status.get("error") or {"status": status.get("status")})[:300]
        for r in status.get("results") or []:
            yield r.get("custom_id"), None, {}, err
        return
    for r in status.get("results") or []:
        resp, err = r.get("response"), r.get("error")
        if err or not resp:
            yield r.get("custom_id"), None, {}, json.dumps(err)[:300]; continue
        b = resp.get("body") or {}
        try:
            text = b["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError):
            text = None
        usage = dict(b.get("usage") or {}, served_by=status.get("provider"), served_model=b.get("model"))
        yield r.get("custom_id"), text, usage, (None if text is not None else "no message in response")
