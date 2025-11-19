# TDS Project 2 – Quiz Answer Machine

An AI-powered agent that visits a quiz web page, figures out what to do, writes Python code to solve the task, and submits the answer back to the quiz server. It is designed specifically for the **LLM Analysis Quiz** project brief.

This README is intentionally verbose so that you can follow it even with limited technical background.

---

## 1. What this project does (in plain English)

Imagine you are given a link like `https://example.com/quiz-834`. When you open it in a browser, some JavaScript runs and shows you a data question, for example:

- “Download this PDF”
- “Find a table”
- “Add up a column called `value`”
- “POST your answer to this URL as JSON”

This project builds a **server** that can:

1. Receive a POST request with:
   - your student `email`
   - your `secret` string (from the Google Form)
   - a quiz `url`
2. Open the quiz page in a **headless browser** (Playwright) so that all JavaScript runs.
3. Read the **text** of the page (and also take a screenshot for future vision use).
4. Send that text to an LLM (e.g. `gpt-5-nano`) which:
   - writes Python code that should solve the quiz, and
   - prints the final answer (only the answer) to stdout.
5. Run that generated Python code in a **sandboxed subprocess**.
6. Take the printed answer and **submit** it as JSON to the quiz’s submit URL.
7. Read the response:
   - If it is correct and gives a new `url`, repeat from step 2 for the new page.
   - If it is correct and has no new `url`, the quiz is done.
   - If it is incorrect, optionally try again (within the time limit).

Your job as a student is to:

- fill in `.env` with your own keys and secrets,
- deploy this service somewhere reachable over HTTPS,
- enter that endpoint URL in the Google Form.

---

## 2. High-level architecture

Files and directories:

- `app.py` – FastAPI app that exposes the `/run` HTTP endpoint.
- `config.py` – loads configuration from environment variables (`.env` file).
- `agent/flow.py` – the **main recursive loop** that actually runs the quiz.
- `agent/llm.py` – wrapper around the OpenAI client (`gpt-5-nano` or similar).
- `agent/prompts.py` – system and user prompts used for the LLM.
- `tools/browser.py` – uses **Playwright** to:
  - render quiz pages (with JavaScript),
  - extract visible text and screenshots,
  - find the submission URL, and
  - POST your answer JSON to that URL.
- `tools/sandbox.py` – runs model-generated Python code in a subprocess.
- `requirements.txt` – Python dependencies.
- `Dockerfile` – container definition (based on the official Playwright Python image).
- `docker-compose.yml` – runs the service easily with Docker Compose.
- `.env.example` – template for environment variables.

Data flow (simplified):

1. **External caller** sends `POST /run` to your server with `{email, secret, url}`.
2. `app.py` checks that `secret` matches your `STUDENT_SECRET`.  
   - If not, it returns **HTTP 403**.
   - If JSON is invalid, it returns **HTTP 400**.
3. `AgentFlow` in `agent/flow.py` starts with `current_url = url`.
4. `BrowserClient.get` in `tools/browser.py`:
   - opens the page with Playwright,
   - waits for network to be idle,
   - gets the page text,
   - takes a full-page screenshot.
5. `LlmClient.plan_and_code` in `agent/llm.py`:
   - sends the page text (and history of previous errors) to the LLM,
   - asks it to generate Python code that prints the answer.
6. `SandboxExecutor.run` in `tools/sandbox.py`:
   - runs the generated code using `python -c ...`,
   - captures `stdout` (answer) and `stderr` (any errors).
7. `LlmClient.parse_answer` cleans up the answer (currently just `strip()`).
8. `BrowserClient.post_answer`:
   - reads the rendered page text to find a **submit URL** (using heuristics like “Post your answer to …”),
   - POSTs JSON: `{email, secret, url: current_url, answer}` to that URL,
   - reads JSON response: `{correct, url?, reason?}`.
9. `AgentFlow`:
   - if `correct` and a new `url` exists → update `current_url` and repeat.
   - if `correct` and there is no new `url` → stop, quiz complete.
   - if `incorrect` → log the reason, maybe retry or move to next URL.
10. When done (or when the time limit expires), `/run` returns a final message like `"Quiz Completed"` or `"Timed out before completing quiz."`.

---

## 3. Requirements

You have two main options:

### Option A – Run with Docker (recommended)

You need:

- **Docker** (https://www.docker.com/)
- **Docker Compose** (often bundled as `docker compose` with newer Docker versions)
- An **OpenAI-compatible API endpoint** and API key:
  - This can be the official OpenAI endpoint.
  - Or a custom endpoint that mimics the OpenAI API.

### Option B – Run directly with Python (for local dev)

You need:

- **Python 3.10+**
- `pip` (Python package manager)

For this project and grading, **Docker is strongly recommended** because it includes all Playwright browser dependencies.

---

## 4. Setting up environment variables

1. Copy the example file:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and fill in:

   - `OPENAI_API_KEY` – your actual key.
   - `OPENAI_BASE_URL` – e.g. `https://api.openai.com/v1` or your custom endpoint.
   - `OPENAI_MODEL` – default is `gpt-5-nano` (you can change if needed).
   - `STUDENT_SECRET` – **must** match the secret you submitted in the Google Form.

3. Keep `.env` **private**. Do not commit it to GitHub.

---

## 5. Running with Docker

1. Build and start the service:

   ```bash
   docker compose up --build
   ```

   This will:

   - build the image defined in `Dockerfile` (based on the Playwright Python image),
   - install all dependencies from `requirements.txt`,
   - start Uvicorn serving `app:app` on port `8000`.

2. Once running, the API will be available at:

   - `http://localhost:8000/run`

3. Test that it responds at all:

   ```bash
   curl -X POST http://localhost:8000/run \
     -H "Content-Type: application/json" \
     -d '{
       "email": "your-email@example.com",
       "secret": "your-secret",
       "url": "https://tds-llm-analysis.s-anand.net/demo"
     }'
   ```

   You should get back JSON like:

   ```jsonc
   {
     "status": "ok",
     "detail": "Timed out before completing quiz."
     // or "Quiz Completed", etc.
   }
   ```

   The exact text depends on how far the agent got within the time limit.

---

## 6. Running locally without Docker (optional)

If you prefer to run directly on your machine:

1. Create and activate a virtual environment (recommended but not required):

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux / macOS
   # .venv\Scripts\activate   # Windows PowerShell
   ```

2. Install dependencies:

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. Install Playwright browsers (only needed once):

   ```bash
   python -m playwright install
   ```

4. Start the FastAPI app with Uvicorn:

   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8000
   ```

5. Test with the same `curl` command as in the Docker section.

---

## 7. API contract and status codes

### Request

- **Method:** `POST`
- **Path:** `/run`
- **Body (JSON):**

  ```jsonc
  {
    "email": "your-email@example.com",
    "secret": "your-secret",
    "url": "https://example.com/quiz-834"
  }
  ```

### Responses

- **200 OK** – accepted and processed:

  ```jsonc
  {
    "status": "ok",
    "detail": "Quiz Completed"
  }
  ```

  The `detail` field is a human-readable summary, for example:

  - `"Quiz Completed"`
  - `"Failed to solve quiz within attempts.""`
  - `"Timed out before completing quiz."`

- **400 Bad Request** – invalid JSON or request body:

  ```jsonc
  {
    "detail": "Invalid JSON or request body",
    "errors": [ /* validation details */ ]
  }
  ```

- **403 Forbidden** – secret does not match `STUDENT_SECRET`:

  ```jsonc
  {
    "detail": "Invalid secret"
  }
  ```

FastAPI automatically handles other errors with 500-series status codes if something unexpected happens.

---

## 8. How the quiz submission works (details)

The quiz pages (like the sample in `project-brief.md`) include instructions such as:

> Post your answer to https://example.com/submit with this JSON payload:
>
> ```jsonc
> {
>   "email": "your email",
>   "secret": "your secret",
>   "url": "https://example.com/quiz-834",
>   "answer": 12345
> }
> ```

The key points:

- **Do not hardcode** any submit URLs.
- Always read them from the page content.

This project does that by:

1. Rendering the page with Playwright and getting the visible text.
2. Searching the text for `http://` or `https://` URLs.
3. Ignoring the quiz URL itself.
4. Preferring URLs that appear near phrases like `"post your answer"` or `"submit"`.
5. Using the best-matching URL as the submit endpoint.
6. Sending the JSON payload described above using `requests.post`.
7. Parsing the JSON response from the quiz server:
   - `correct: true/false`
   - optional `url` – the next quiz URL
   - optional `reason` – why it was wrong, or other info

This is intentionally general so that it can handle many different quiz pages, as long as they follow the pattern from the project brief.

---

## 9. Where the prompts live

The LLM prompt strategy is defined in `agent/prompts.py`:

- `SYSTEM_PROMPT` – focused on:
  - solving computational quizzes only,
  - never leaking secrets,
  - replying with `ACCESS_DENIED` if asked for the code word.
- `USER_OVERRIDE_PROMPT` – a “break the system prompt” style user prompt (for the separate prompt-competition part of the project).

The code in `agent/llm.py` uses `SYSTEM_PROMPT` and constructs an additional user message that describes:

- the page text,
- previous errors,
- and asks the model to output Python code that prints only the final answer.

You are free to tune these prompts further as long as the behaviour stays within the project rules.

---

## 10. Things you may want to extend

Once the basics work, you can improve:

- **Vision support** – pass the screenshot from `BrowserClient.get` to the LLM as an image input, so the model can read charts/tables that aren’t in plain text.
- **Safer sandbox** – restrict what the generated Python code can do (timeouts, memory limits, allowed imports, etc.).
- **Better URL detection** – tighten the heuristics for finding the submit URL.
- **Logging & monitoring** – keep structured logs of each quiz run to help debug and explain your viva answers.

---

## 11. Troubleshooting

- If Playwright fails to launch the browser:
  - Make sure you are using the Docker setup (which includes browsers), or
  - On local Python, run `python -m playwright install`.
- If you always see `"Timed out before completing quiz."`:
  - Check that your `OPENAI_API_KEY` / `OPENAI_BASE_URL` are correct.
  - Verify that the quiz URL is reachable from where you are running the container.
- If you get `403 Invalid secret` from `/run`:
  - Ensure `secret` in your POST body matches `STUDENT_SECRET` in `.env`.

With this README and the existing code, you should be able to:

- run the service locally,
- hook it up to the demo endpoint from the project brief,
- and then deploy it to your own HTTPS endpoint for grading.
