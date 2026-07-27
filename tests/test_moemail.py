import unittest
from unittest.mock import patch

from requests.exceptions import SSLError


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.raised = False

    def raise_for_status(self):
        self.raised = True

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class MoeMailRequestTests(unittest.TestCase):
    def test_dispatches_get_and_post_with_a_shared_request_helper(self):
        from registration.moemail import _request

        get_response = FakeResponse({"method": "get"})
        post_response = FakeResponse({"method": "post"})
        session = FakeSession([get_response, post_response])

        self.assertEqual(
            _request(session, "get", "https://mail.test/config", params={"cursor": "1"}),
            {"method": "get"},
        )
        self.assertEqual(
            _request(session, "post", "https://mail.test/emails", json={"name": "test"}),
            {"method": "post"},
        )
        self.assertEqual(session.calls, [
            ("get", "https://mail.test/config", {"timeout": 15, "params": {"cursor": "1"}}),
            ("post", "https://mail.test/emails", {"timeout": 15, "json": {"name": "test"}}),
        ])
        self.assertTrue(get_response.raised)
        self.assertTrue(post_response.raised)

    def test_retries_ssl_errors_before_returning_a_response(self):
        from registration.moemail import _request

        response = FakeResponse({"ok": True})
        session = FakeSession([SSLError("temporary"), response])

        with patch("registration.moemail.time.sleep") as sleep:
            self.assertEqual(_request(session, "get", "https://mail.test/config"), {"ok": True})

        self.assertEqual(len(session.calls), 2)
        sleep.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
