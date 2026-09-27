import importlib.util
import io
import os
import unittest
from contextlib import redirect_stderr
from datetime import date
from pathlib import Path
from unittest.mock import patch

import httpx

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "sentiment-analysis"
    / "scripts"
    / "adanos_sentiment.py"
)


def load_script():
    spec = importlib.util.spec_from_file_location("adanos_sentiment", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AdanosSentimentTests(unittest.TestCase):
    def test_stock_sources_and_crypto_reddit_keep_their_own_paths(self):
        module = load_script()
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={"found": False, "daily_trend": None})

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            for source in module.STOCK_PATHS:
                result = module.fetch_sentiment(
                    client,
                    asset_class="stock",
                    symbol="AAPL",
                    source=source,
                    start=date(2026, 9, 1),
                    end=date(2026, 9, 7),
                    api_key="test-key",
                )
                self.assertFalse(result["found"])
            module.fetch_sentiment(
                client,
                asset_class="crypto",
                symbol="BTC",
                source="reddit",
                start=date(2026, 9, 1),
                end=date(2026, 9, 7),
                api_key="test-key",
            )

        self.assertEqual(
            [request.url.path for request in requests],
            [f"{path}/AAPL" for path in module.STOCK_PATHS.values()]
            + ["/reddit/crypto/v1/token/BTC"],
        )
        for request in requests:
            self.assertEqual(request.headers["X-API-Key"], "test-key")
            self.assertEqual(request.url.params["from"], "2026-09-01")
            self.assertEqual(request.url.params["to"], "2026-09-07")
            self.assertNotIn("test-key", str(request.url))
            self.assertNotIn("days", request.url.params)

    def test_crypto_rejects_stock_only_source_before_request(self):
        module = load_script()
        with (
            httpx.Client(transport=httpx.MockTransport(lambda _: None)) as client,
            self.assertRaisesRegex(ValueError, "Reddit only"),
        ):
            module.fetch_sentiment(
                client,
                asset_class="crypto",
                symbol="BTC",
                source="news",
                start=date(2026, 9, 1),
                end=date(2026, 9, 7),
                api_key="test-key",
            )

    def test_cli_redacts_key_on_api_error(self):
        module = load_script()
        client = httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(403))
        )
        stderr = io.StringIO()
        with (
            patch.dict(os.environ, {"ADANOS_API_KEY": "secret-test-key"}),
            patch.object(module.httpx, "Client", return_value=client),
            redirect_stderr(stderr),
        ):
            exit_code = module.main(
                ["AAPL", "--from", "2026-09-01", "--to", "2026-09-07"]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("HTTP 403", stderr.getvalue())
        self.assertNotIn("secret-test-key", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
