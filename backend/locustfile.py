from locust import HttpUser, constant, task


class ResearchUser(HttpUser):
    wait_time = constant(1)

    @task
    def run_research(self):
        with self.client.get(
            "/api/research/start",
            params={"ticker": "AAPL"},
            name="/api/research/start",
            stream=True,
            catch_response=True,
            timeout=240,
        ) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}")
                return

            completed = False

            for raw_line in response.iter_lines(decode_unicode=True):
                line = (
                    raw_line.decode("utf-8", errors="replace")
                    if isinstance(raw_line, bytes)
                    else raw_line
                )

                if line == "event: complete":
                    completed = True
                elif line == "event: error":
                    response.failure("Research pipeline returned an error")
                    return

            if completed:
                response.success()
            else:
                response.failure("Stream ended before the complete event")