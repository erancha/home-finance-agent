#!/usr/bin/env bash
# Settings of this deployment that are its own and no secret. ./scripts/init-env.sh copies this
# file to lib/params.sh (gitignored); fill it in there. Every line is a plain export KEY="value":
# the scripts source the file, and the agent started on the host reads it too.

# Required: provider:model of the model that writes the report, for the provider anthropic or
# openai. The model only phrases totals computed in code, so the cheapest tier does, e.g.
# openai:gpt-5-nano or anthropic:claude-haiku-5-5. A GPT-5 model is asked for minimal reasoning
# effort, since on its default a few sentences can take over a minute. Fill in by hand.
export LLM_MODEL=""

# Required: the OAuth client ID of the page's Sign in with Google button, which every ID token
# must name as its audience. Fill in by hand (docs/sign-in.md).
export GOOGLE_CLIENT_ID=""

# Optional: the address the README and NOTICE give for a commercial license. Tracked files may
# show this address; the pre-commit hook refuses any other address of this file.
export LICENSE_CONTACT=""
