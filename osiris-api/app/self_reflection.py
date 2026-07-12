def evaluate_execution(execution: dict) -> dict:
    score = 100
    problems = []

    for result in execution.get("results", []):
        step = result.get("step", "unknown")
        status = result.get("status", "unknown")
        output = str(result.get("output", "")).lower()

        if status != "success":
            score -= 40
            problems.append(f"{step} failed")

        if "error" in output or "exception" in output or "failed" in output:
            score -= 20
            problems.append(f"{step} returned an error-like result")

    score = max(0, min(score, 100))

    return {
        "success": score >= 70,
        "score": score,
        "problems": problems,
    }
