"""Checks the EC2 template for values AWS rejects only when the stack is created.

cfn-lint passes a security group rule description with characters EC2 refuses, so the creation
fails and rolls back; EC2 accepts only letters, digits, spaces and ._-:/()#,@[]+=&;{}!$*.
"""

import re
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[2] / "scripts" / "template-ec2.yaml"
EC2_DESCRIPTION = re.compile(r"[A-Za-z0-9. _\-:/()#,@\[\]+=&;{}!$*]{0,255}")


def test_security_group_descriptions_use_only_characters_ec2_accepts() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    block = text.split("  SecurityGroup:\n", 1)[1].split("\n\n", 1)[0]
    descriptions = re.findall(r"(?:Group)?Description: (.+)", block)
    assert len(descriptions) == 3
    for description in descriptions:
        assert EC2_DESCRIPTION.fullmatch(description), description
