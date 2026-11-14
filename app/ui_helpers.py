"""Formatting helpers shared by the pages and dialogs."""
from . import dns_bench as bench
from .skin import tr


def fmt_ms(v):
    return "—" if v is None else f"{round(v)} ms"


def fmt_pct(v):
    if v is None:
        return "—"
    v = round(v, 1)
    return f"{v:g}%"


def no_reply(res):
    """True when the server did not really answer: nothing came back, or it gave up after consecutive timeouts."""
    return bool(res) and res.get("status") in (bench.TIMEOUT, bench.UNAVAILABLE, bench.INCOMPLETE)


def value_grade(res):
    """Colour grade of the big number: a server that did not answer is always red (never grey / green)."""
    return "bad" if no_reply(res) else bench.grade(res)


def stat_text(res, key):
    """Average / jitter text of a result: TIMEOUT / UNAVAILABLE when the server did not answer."""
    if not res:
        return "—"
    if no_reply(res):
        return tr("st_unavailable") if res.get("status") == bench.UNAVAILABLE else tr("st_timeout")
    return fmt_ms(res.get(key))


def big_value(res):
    """Text for the prominent 'Last Ping' number of a result (or None)."""
    if not res:
        return "— ms"
    if no_reply(res):
        return tr("st_unavailable") if res.get("status") == bench.UNAVAILABLE else tr("st_timeout")
    return fmt_ms(res.get("last"))


def status_text(res):
    if not res:
        return tr("not_tested")
    return {bench.OK: tr("st_ok"), bench.INCOMPLETE: tr("st_incomplete"), bench.TIMEOUT: tr("st_timeout"),
            bench.UNAVAILABLE: tr("st_unavailable")}.get(res.get("status"), "")


def _value(res, mode):
    """(usable?, number) of one server's result for the chosen sort column, rounded as displayed."""
    if not res or res.get("status") not in (bench.OK, bench.INCOMPLETE):
        return None
    v = res.get({"avg": "avg", "jitter": "jitter", "loss": "loss", "last": "last"}[mode])
    if v is None:
        return None
    return round(v, 1) if mode == "loss" else round(v)


def rank_key(res, res2, mode):
    """Primary decides; if two DNS tie on Primary (e.g. 29 ms vs 29 ms) the better Secondary wins."""
    if not res:
        return (3, 0, 0)
    rank = 0 if res.get("status") == bench.OK else 1 if res.get("status") == bench.INCOMPLETE else 2
    if rank == 2:
        return (2, 0, 0)
    p = _value(res, mode)
    s = _value(res2, mode)
    return (rank, p if p is not None else 1e9, s if s is not None else 1e9)
