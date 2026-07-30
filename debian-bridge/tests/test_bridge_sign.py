from casual_board_bridge.main import sign_result, stub_executor


def test_sign_includes_nonce():
    a = sign_result(
        "secret",
        job_id="job-1",
        status="completed",
        worker_id="w",
        lease_nonce="abc",
        result={"x": 1},
        message="ok",
        board_patch=None,
    )
    b = sign_result(
        "secret",
        job_id="job-1",
        status="completed",
        worker_id="w",
        lease_nonce="abc",
        result={"x": 1},
        message="ok",
        board_patch=None,
    )
    assert a == b
    c = sign_result(
        "secret",
        job_id="job-1",
        status="completed",
        worker_id="w",
        lease_nonce="DIFFERENT",
        result={"x": 1},
        message="ok",
        board_patch=None,
    )
    assert a != c


def test_stub_not_claiming_hermes():
    out = stub_executor({"command": "set_machine", "payload": {"disk_pct": 1}})
    assert "stub" in out["executor_note"].lower()
