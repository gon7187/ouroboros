import os
import time
from openai import OpenAI

# Test question
TEST_QUESTION = "Какой самый эффективный способ получения бесплатного трафика на Wildberries в 2025 году? Ответ кратко, по делу."

# Results tracking
results = []

def test_model(name, client, model, is_free=True):
    """Test a single model."""
    print(f"\n{'='*60}")
    print(f"Testing: {name} ({model})")
    print(f"Free: {is_free}")
    print(f"{'='*60}")
    
    try:
        start = time.time()
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": TEST_QUESTION}],
            max_tokens=500
        )
        elapsed = time.time() - start
        
        msg = resp.choices[0].message.content
        usage = resp.usage
        
        print(f"\nResponse ({elapsed:.2f}s):")
        print(msg[:300] + "..." if len(msg) > 300 else msg)
        print(f"\nTokens: {usage.prompt_tokens} + {usage.completion_tokens} = {usage.total_tokens}")
        
        results.append({
            "name": name,
            "model": model,
            "free": is_free,
            "time": elapsed,
            "tokens": usage.total_tokens,
            "response": msg
        })
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

# Test 1: Z.ai - glm-4.7-flashx (fast, free)
try:
    zai_client = OpenAI(
        base_url="https://api.z.ai/api/coding/paas/v4",
        api_key="e19def33bcd04ca08c9da1653e1accde.r7Ame4c6dVLrmKFT"
    )
    test_model("Z.ai Flash", zai_client, "glm-4.7-flashx", is_free=True)
except Exception as e:
    print(f"Z.ai setup failed: {e}")

# Test 2: OpenCode - kimi-k2.5-free (free tier)
try:
    opencode_client = OpenAI(
        base_url="https://api.opencode.ai/v1",
        api_key="sk-kKxq8nwze33meTFd982shUdJ8sNdozU5aIP2F4RidtcDeGsAMVBiqXWFsklf0ZJO"
    )
    test_model("OpenCode Kimi", opencode_client, "opencode/kimi-k2.5-free", is_free=True)
except Exception as e:
    print(f"OpenCode setup failed: {e}")

# Test 3: OpenAI Codex - gpt-5.3-codex (paid but powerful)
try:
    codex_client = OpenAI(
        base_url="https://api.openai.com/v1",
        api_key="eyJhbGciOiJSUzI1NiIsImtpZCI6IjE5MzQ0ZTY1LWJiYzktNDRkMS1hOWQwLWY5NTdiMDc5YmQwZSIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS92MSJdLCJjbGllbnRfaWQiOiJhcHBfRU1vYW1FRVo3M2YwQ2tYYVhwN2hyYW5uIiwiZXhwIjoxNzcxNzkyNjExLCJodHRwczovL2FwaS5vcGVuYWkuY29tL2F1dGgiOnsiY2hhdGdwdF9hY2NvdW50X2lkIjoiMjE4Njg1MzUtZDI4NS00MTMwLTg0N2ItMTA5Mzc0MDEyNTI1IiwiY2hhdGdwdF9hY2NvdW50X3VzZXJfaWQiOiJ1c2VyLVVkUER0Y2xXemJSak5MWDF6dWl0NEtNVl9fMjE4Njg1MzUtZDI4NS00MTMwLTg0N2ItMTA5Mzc0MDEyNTI1IiwiY2hhdGdwdF9jb21wdXRlX3Jlc2lkZW5jeSI6Im5vX2NvbnN0cmFpbnQiLCJjaGF0Z3B0X3BsYW5fdHlwZSI6InBybyIsImNoYXRncHRfdXNlcl9pZCI6InVzZXItVWRQRHRjbFd6YlJqTkxYMXp1aXQ0S01WIiwidXNlcl9pZCI6InVzZXItVWRQRHRjbFd6YlJqTkxYMXp1aXQ0S01WIn0sImh0dHBzOi8vYXBpLm9wZW5haS5jb20vbWZhIjp7InJlcXVpcmVkIjoieWVzIn0sImh0dHBzOi8vYXBpLm9wZW5haS5jb20vcHJvZmlsZSI6eyJlbWFpbCI6Im5vb2JseWFhQGdtYWlsLmNvbSIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlfSwiaWF0IjoxNzcwOTI4NjExLCJpc3MiOiJodHRwczovL2F1dGgub3BlbmFpLmNvbSIsImp0aSI6ImQyYTQ0MmJhLTg0MzQtNDEwNC1iMzczLWMxZGZiN2Q1NTE4MSIsIm5iZiI6MTc3MDkyODYxMSwicHdkX2F1dGhfdGltZSI6MTc3MDkyODYwOTg4Mywic2NwIjpbIm9wZW5pZCIsInByb2ZpbGUiLCJlbWFpbCIsIm9mZmxpbmVfYWNjZXNzIl0sInNlc3Npb25faWQiOiJhdXRoc2Vzc19WZWN4Qm9ZdHFRd0h0REMxNHJ6ZnlWVjciLCJzdWIiOiJhdXRoMHw2NGFlYzkzNTFjYjgzZjIxYjdlMmQzZmEifQ.swLAZEI1BE_t_Gb395Z55a9KgL_VGOm9YrZn7RfTf6fT0iPS9CEmLxdZ4j-v5TBiZRDADHGvMIKYocVPE9cJbE0WMApNU9qG0eCT2jVsF7DL9ZffJt7Jh0lntUa2klkTSK37nC_pKZYQMsolwFgmxLmG44uEZwISKp7fyLV3EI2sCXBffZ548SxH816Bzjs2EhJMqwKJTuVVxHXX1DadtAJGq1oY8Lt98cNX7GH93QB6xPcW25GOcl8Fu69eS22koOksSnJL5bJpOJKCsP91QyeIKIJTNoVaLjGREPEtCxfJuyvsKZVKDmMwdpBXwDWj7Nm4hYuRwQEDqN_OLcoWl45Ceodph0ACgLkkEvfJe7J87Hzs-JL-68X30bTHGXtS3VhdV-60O3QRAeL7W3_VC4zVsZfa26tZ762YrliseOmY0C3-zJbYs1XKjoP90bR498rQ5t-eoGDQTUT0Ou4WEfleEhw1wN2PzUxTMH0VGhOnWMPn4mXHpqXXNk8t9Phwbc1x35odkIkONoQzGE1ebvyOFnGuitOwGfwjj79fYjiptLPAOryi3TuclwFauZsY7kxd7H878n20LIXMIHcxO5izeoRaW35KqENwiBpAASPRtFUwAuq0tJlLQtvirdC5Z6rsGM0lQox7fsVoLtQ8uR9OY5ujxC1FlsZngL8UDjY"
    )
    test_model("OpenAI Codex", codex_client, "gpt-5.3-codex", is_free=False)
except Exception as e:
    print(f"Codex setup failed: {e}")

# Summary
print(f"\n\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
for r in results:
    print(f"{r['name']}: {r['time']:.2f}s, {r['tokens']} tokens, Free={r['free']}")
