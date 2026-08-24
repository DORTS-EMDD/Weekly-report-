import os
import unittest
from unittest import mock

import requests

import maiagent_service


class MaiAgentTimeoutTests(unittest.TestCase):
    def test_retry_prompt_lists_multi_candidate_blocks_and_requires_split(self):
        prompt = maiagent_service.build_report_retry_prompt(
            "original prompt",
            "previous response",
            {
                "missing_ids": [],
                "unknown_ids": [],
                "duplicate_ids": [],
                "multi_candidate_model_blocks": [[9, 12]],
                "content_quality_issues": [],
            },
        )

        self.assertIn("多候選 marker block：[[9, 12]]", prompt)
        self.assertIn("每個正式新聞 block 必須且只能包含一個 candidate marker", prompt)
        self.assertIn("各自獨立的完整新聞 block", prompt)
        self.assertIn("不得合併", prompt)
        self.assertIn("所有有效 candidate IDs 必須各出現一次", prompt)

    def _call(self, http_client):
        return maiagent_service.call_maiagent_cloud(
            "fixture prompt",
            api_key="fixture-api-key",
            chatbot_id="fixture-chatbot",
            api_base="https://example.invalid",
            http_client=http_client,
        )

    def test_default_timeouts(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                maiagent_service.get_maiagent_timeout_seconds(),
                (15, 660),
            )

    def test_environment_override(self):
        with mock.patch.dict(
            os.environ,
            {
                "MAIAGENT_CONNECT_TIMEOUT_SECONDS": "22",
                "MAIAGENT_READ_TIMEOUT_SECONDS": "720",
            },
            clear=True,
        ):
            self.assertEqual(
                maiagent_service.get_maiagent_timeout_seconds(),
                (22, 720),
            )

    def test_invalid_environment_values_use_defaults(self):
        with mock.patch.dict(
            os.environ,
            {
                "MAIAGENT_CONNECT_TIMEOUT_SECONDS": "not-a-number",
                "MAIAGENT_READ_TIMEOUT_SECONDS": "999999",
            },
            clear=True,
        ):
            self.assertEqual(
                maiagent_service.get_maiagent_timeout_seconds(),
                (15, 660),
            )

    def test_post_receives_connect_and_read_timeout_tuple(self):
        http_client = mock.Mock()
        response = http_client.post.return_value
        response.status_code = 200
        response.text = "ok"
        response.headers = {}
        response.json.return_value = {"content": "ok"}

        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self._call(http_client), "ok")

        self.assertEqual(
            http_client.post.call_args.kwargs["timeout"],
            (15, 660),
        )

    def test_read_timeout_keeps_readable_error_and_timeout_diagnostic(self):
        http_client = mock.Mock()
        http_client.post.side_effect = requests.ReadTimeout("read timed out")

        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                RuntimeError,
                r"(?s)MaiAgent API 所有嘗試均失敗.*read=660s",
            ) as context:
                self._call(http_client)

        self.assertIn("Request error: read timed out", str(context.exception))
        self.assertNotIn("fixture-api-key", str(context.exception))


if __name__ == "__main__":
    unittest.main()
