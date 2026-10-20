"""A continuously yielding response cannot extend the overall HTTP deadline."""

import asyncio
import threading
import time

import httpx
import pytest

from sre_agent import llm


@pytest.mark.parametrize("inside_loop", [False, True])
def test_total_deadline_cancels_continuous_response_and_closes_before_return(
    monkeypatch, inside_loop
):
    observed = {"closed": False, "cancelled": False, "fragments": 0}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            observed["closed"] = True

        async def post(self, *_args, **_kwargs):
            try:
                for _ in range(100):
                    await asyncio.sleep(0.01)
                    observed["fragments"] += 1
                pytest.fail("Continuous bytes must not extend the absolute deadline")
            except asyncio.CancelledError:
                observed["cancelled"] = True
                raise

    monkeypatch.setattr(llm.httpx, "AsyncClient", Client)

    def call():
        with pytest.raises(httpx.ReadTimeout, match="Échéance totale"):
            llm._poster_borne("http://synthetic.invalid", headers={}, json={}, timeout=0.05)

    async def embedded():
        call()

    started = time.monotonic()
    asyncio.run(embedded()) if inside_loop else call()
    assert time.monotonic() - started < 0.75
    assert observed["closed"] and observed["cancelled"]
    assert observed["fragments"] < 100
    assert not any(t.name.startswith("sre-http") for t in threading.enumerate())


def test_successful_exchange_is_returned_after_client_close(monkeypatch):
    closed = []
    response = httpx.Response(200, json={"choices": []})

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            closed.append(True)

        async def post(self, *_args, **_kwargs):
            return response

    monkeypatch.setattr(llm.httpx, "AsyncClient", Client)
    assert llm._poster_borne("http://synthetic.invalid", headers={}, json={}, timeout=1) is response
    assert closed == [True]
