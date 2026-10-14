# SPDX-License-Identifier: MIT
"""Local launches must not fetch the hosted CLI migration message."""


def test_local_mode_skips_motd_http(monkeypatch):
    import atopile.cli.motd as motd

    monkeypatch.setenv("ATOPILE_LOCAL_MODE", "1")
    monkeypatch.setattr(motd, "_shown", False)

    def forbidden(*args, **kwargs):
        raise AssertionError("Local CLI attempted an online MOTD request")

    monkeypatch.setattr(motd.httpx, "get", forbidden)
    motd.maybe_show_motd()
    assert motd._shown is False
