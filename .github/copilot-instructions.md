# Project Instructions

- Follow the existing architecture and keep the frontend and backend responsibilities clearly separated.
- Never expose secrets, hard-code API keys, or put private API keys in frontend code. Use environment variables and never commit `.env` files or credentials.
- Prefer reusable components, avoid duplicate code, and do not add unnecessary dependencies.
- Use TypeScript types properly in the frontend and Python type hints in the backend.
- Validate API input and handle errors explicitly; do not silently swallow exceptions.
- Keep database access organized as database functionality is introduced.
- Put AI providers behind provider/service interfaces. Do not tightly couple application logic to Gemini; keep Groq and Ollama interchangeable with it.
- Write maintainable code and update documentation when the architecture changes.
- Do not implement features that were not requested.
- Run appropriate checks and tests before considering a task complete.
