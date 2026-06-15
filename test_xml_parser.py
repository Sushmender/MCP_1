"""
Quick smoke-test for GroqProvider._parse_xml_function_calls.
Run with:  python test_xml_parser.py
"""
import sys
sys.path.insert(0, ".")

from app.llm.groq_provider import GroqProvider

parse = GroqProvider._parse_xml_function_calls

CASES = [
    # (description, input_text, expected_name, expected_args)
    (
        "bare object",
        '<function=list_directory{"path": "papers"}</function>',
        "list_directory",
        {"path": "papers"},
    ),
    (
        "array-wrapped",
        '<function=list_directory [{"path": "papers"}] </function>',
        "list_directory",
        {"path": "papers"},
    ),
    (
        "bare object missing closing brace",
        '<function=list_directory{"path": "papers/"}</function>',
        "list_directory",
        {"path": "papers/"},
    ),
    (
        "array-wrapped with trailing space",
        '<function=list_directory [{"path": "papers"}]  </function>',
        "list_directory",
        {"path": "papers"},
    ),
    (
        "tool with multiple args",
        '<function=search_papers {"query": "AI", "max_results": 5}</function>',
        "search_papers",
        {"query": "AI", "max_results": 5},
    ),
    (
        "= separator between name and args (new variant)",
        '<function=list_directory={"path": "papers"}</function>',
        "list_directory",
        {"path": "papers"},
    ),
]

passed = 0
failed = 0
for desc, text, exp_name, exp_args in CASES:
    calls = parse(text)
    ok = (
        len(calls) == 1
        and calls[0]["name"] == exp_name
        and calls[0]["input"] == exp_args
    )
    if ok:
        passed += 1
        print(f"  [PASS] {desc}")
    else:
        failed += 1
        got_name = calls[0]["name"] if calls else "NO MATCH"
        got_args = calls[0]["input"] if calls else {}
        print(f"  [FAIL] {desc}")
        print(f"         got  name={got_name!r}  args={got_args!r}")
        print(f"         want name={exp_name!r}  args={exp_args!r}")

print(f"\n{passed}/{passed+failed} tests passed")
sys.exit(0 if failed == 0 else 1)
