from __future__ import annotations

import argparse
import os

import asana as asana_sdk
from asana_util import asana_client, extract_task_gid


def main() -> None:
    parser = argparse.ArgumentParser(description="Add a comment to an Asana task.")
    parser.add_argument("task", help="Task gid or URL")
    parser.add_argument("--comment", default="", help="Comment text")
    parser.add_argument("--pr-url", default="", help="PR URL to include in the comment")
    args = parser.parse_args()

    if not args.comment and not args.pr_url:
        raise RuntimeError("Provide --comment or --pr-url")

    token = os.getenv("ASANA_TOKEN")
    if not token:
        raise RuntimeError("ASANA_TOKEN is required")

    task_gid = extract_task_gid(args.task)
    text = args.comment if args.comment else f"PR: {args.pr_url}"

    client = asana_client(token)
    stories_api = asana_sdk.StoriesApi(client)
    stories_api.create_story_for_task({"data": {"text": text}}, task_gid, {})


if __name__ == "__main__":
    main()
