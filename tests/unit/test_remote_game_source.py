import httpx
import pytest
import respx

from backend.game_sources.base import ActionId, GameSourceError
from backend.game_sources.remote import RemoteGameSource, list_remote_games

BASE_URL = "https://three.arcprize.org"


def frame_response(guid="guid-1", state="NOT_FINISHED", available_actions=None):
    return {
        "game_id": "ls20",
        "guid": guid,
        "frame": [[[0] * 64 for _ in range(64)]],
        "state": state,
        "levels_completed": 0,
        "win_levels": 3,
        "action_input": {"id": 0, "data": None, "reasoning": None},
        "available_actions": available_actions or [1, 2, 3, 4, 5, 6],
        "full_reset": True,
    }


@pytest.mark.asyncio
@respx.mock
async def test_reset_opens_scorecard_then_resets_with_card_id():
    open_route = respx.post(f"{BASE_URL}/api/scorecard/open").mock(
        return_value=httpx.Response(200, json={"card_id": "card-1"})
    )
    reset_route = respx.post(f"{BASE_URL}/api/cmd/RESET").mock(
        return_value=httpx.Response(200, json=frame_response())
    )

    source = RemoteGameSource("ls20", "test-key", base_url=BASE_URL)
    frame_data = await source.reset()

    import json

    assert open_route.called
    reset_body = json.loads(reset_route.calls.last.request.content)
    assert reset_body == {"game_id": "ls20", "card_id": "card-1"}
    assert frame_data.guid == "guid-1"
    assert frame_data.source == "remote"
    assert frame_data.state.value == "NOT_FINISHED"

    respx.post(f"{BASE_URL}/api/scorecard/close").mock(return_value=httpx.Response(200, json={}))
    await source.close()


@pytest.mark.asyncio
@respx.mock
async def test_second_reset_uses_guid_not_card_id():
    respx.post(f"{BASE_URL}/api/scorecard/open").mock(
        return_value=httpx.Response(200, json={"card_id": "card-1"})
    )
    respx.post(f"{BASE_URL}/api/cmd/RESET").mock(
        return_value=httpx.Response(200, json=frame_response())
    )

    source = RemoteGameSource("ls20", "test-key", base_url=BASE_URL)
    await source.reset()
    reset_route = respx.post(f"{BASE_URL}/api/cmd/RESET").mock(
        return_value=httpx.Response(200, json=frame_response(guid="guid-1"))
    )
    await source.reset()

    import json

    second_body = json.loads(reset_route.calls.last.request.content)
    assert second_body == {"game_id": "ls20", "guid": "guid-1"}

    respx.post(f"{BASE_URL}/api/scorecard/close").mock(return_value=httpx.Response(200, json={}))
    await source.close()


@pytest.mark.asyncio
@respx.mock
async def test_step_action6_puts_xy_top_level_not_nested():
    respx.post(f"{BASE_URL}/api/scorecard/open").mock(
        return_value=httpx.Response(200, json={"card_id": "card-1"})
    )
    respx.post(f"{BASE_URL}/api/cmd/RESET").mock(
        return_value=httpx.Response(200, json=frame_response())
    )
    action_route = respx.post(f"{BASE_URL}/api/cmd/ACTION6").mock(
        return_value=httpx.Response(200, json=frame_response())
    )

    source = RemoteGameSource("ls20", "test-key", base_url=BASE_URL)
    await source.reset()
    await source.step(ActionId.ACTION6, x=12, y=34)

    import json

    body = json.loads(action_route.calls.last.request.content)
    assert body == {"game_id": "ls20", "guid": "guid-1", "x": 12, "y": 34}
    assert "data" not in body

    respx.post(f"{BASE_URL}/api/scorecard/close").mock(return_value=httpx.Response(200, json={}))
    await source.close()


@pytest.mark.asyncio
@respx.mock
async def test_step_before_reset_raises():
    source = RemoteGameSource("ls20", "test-key", base_url=BASE_URL)
    with pytest.raises(GameSourceError, match="before reset"):
        await source.step(ActionId.ACTION1)


@pytest.mark.asyncio
@respx.mock
async def test_reset_action_delegates_to_reset():
    respx.post(f"{BASE_URL}/api/scorecard/open").mock(
        return_value=httpx.Response(200, json={"card_id": "card-1"})
    )
    reset_route = respx.post(f"{BASE_URL}/api/cmd/RESET").mock(
        return_value=httpx.Response(200, json=frame_response())
    )

    source = RemoteGameSource("ls20", "test-key", base_url=BASE_URL)
    await source.reset()
    await source.step(ActionId.RESET)

    assert reset_route.call_count == 2

    respx.post(f"{BASE_URL}/api/scorecard/close").mock(return_value=httpx.Response(200, json={}))
    await source.close()


@pytest.mark.asyncio
@respx.mock
async def test_http_error_raises_game_source_error():
    respx.post(f"{BASE_URL}/api/scorecard/open").mock(
        return_value=httpx.Response(200, json={"card_id": "card-1"})
    )
    respx.post(f"{BASE_URL}/api/cmd/RESET").mock(return_value=httpx.Response(401))

    source = RemoteGameSource("ls20", "test-key", base_url=BASE_URL)
    with pytest.raises(GameSourceError):
        await source.reset()


@pytest.mark.asyncio
@respx.mock
async def test_close_closes_scorecard_with_card_id():
    respx.post(f"{BASE_URL}/api/scorecard/open").mock(
        return_value=httpx.Response(200, json={"card_id": "card-1"})
    )
    respx.post(f"{BASE_URL}/api/cmd/RESET").mock(
        return_value=httpx.Response(200, json=frame_response())
    )
    close_route = respx.post(f"{BASE_URL}/api/scorecard/close").mock(
        return_value=httpx.Response(200, json={})
    )

    source = RemoteGameSource("ls20", "test-key", base_url=BASE_URL)
    await source.reset()
    await source.close()

    import json

    assert json.loads(close_route.calls.last.request.content) == {"card_id": "card-1"}


@pytest.mark.asyncio
@respx.mock
async def test_list_remote_games_parses_response():
    respx.get(f"{BASE_URL}/api/games").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"game_id": "ls20", "title": "Locksmith", "tags": ["public"]},
                {"game_id": "ft09", "title": None, "tags": None},
            ],
        )
    )

    games = await list_remote_games("test-key", base_url=BASE_URL)

    assert [g.game_id for g in games] == ["ls20", "ft09"]
    assert games[0].title == "Locksmith"
    assert games[0].source == "remote"
