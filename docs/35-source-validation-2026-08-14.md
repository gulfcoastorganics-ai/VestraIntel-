# v1.5 source/product validation — 2026-08-14

The GPT integration was checked against current official OpenAI product documentation on August 14, 2026.

## Custom GPT builder

OpenAI's current help documentation states that GPT creation/editing is available on the ChatGPT web experience for paid users with appropriate permissions. GPTs can be created from the GPTs area using the conversational builder or direct configuration view.

Official source:
https://help.openai.com/en/articles/8554397-creating-a-gp

## GPT Actions

OpenAI documents GPT Actions as the mechanism for connecting a GPT to an external API defined by an OpenAPI JSON/YAML schema. Supported authentication options include none, API key, and OAuth. API-key authentication can use bearer authentication. The editor supports importing or pasting an OpenAPI schema and testing actions in Preview.

Official source:
https://help.openai.com/en/articles/9442513

## Apps vs Actions

Current GPT configuration documentation states that a GPT can use Apps or Actions, but not both at the same time. Vestra Intel therefore uses Actions for the FIA backend.

Official source:
https://help.openai.com/en/articles/8554397-creating-a-gp

## Knowledge files

The current GPT documentation permits up to 20 knowledge files, each up to 512 MB. v1.5 provides four text-forward knowledge files so the live FIA database can remain in the backend rather than being embedded in GPT Knowledge.

Official source:
https://help.openai.com/en/articles/8554397-creating-a-gp

## Privacy policy and public sharing

OpenAI's Actions documentation says public GPTs using Actions must include a valid privacy-policy URL. v1.5 exposes `/privacy` as a starting policy page. Before public distribution, the operator should add a real business contact and confirm the deployed policy matches actual hosting/logging practices.

Official source:
https://help.openai.com/en/articles/9442513

## Model compatibility

OpenAI notes that custom Actions are not available in Pro mode and that the editor presents action-compatible model choices when Actions are configured. The Vestra Intel setup guide therefore does not hard-code a model name that may change over time.
