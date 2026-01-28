#!/usr/bin/env python3
"""Launch multiple training runs with sequential run IDs.

Example usage:
    python scripts/launch_multiple_runs.py \
        recipes.prod.arena_basic_easy_shaped.train \
        run=av.abes.experience.01.26.0x \
        --no-spot --gpus 4 \
        --num-runs 1
"""

import argparse
import subprocess
import sys
import threading
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Launch multiple training runs with sequential run IDs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
The run name should contain '0x' which will be replaced with zero-padded numbers
starting from 01. For example, 'run=av.abes.experience.01.26.0x' will become:
  - av.abes.experience.01.26.01
  - av.abes.experience.01.26.02
  - av.abes.experience.01.26.03
  etc.
        """,
    )
    parser.add_argument(
        "module_path",
        help="Module path (e.g., recipes.prod.arena_basic_easy_shaped.train)",
    )
    parser.add_argument(
        "run_template",
        help="Run name template with '0x' placeholder (e.g., run=av.abes.experience.01.26.0x)",
    )
    parser.add_argument(
        "--num-runs",
        type=int,
        default=1,
        help="Number of runs to launch (default: 1)",
    )
    parser.add_argument(
        "--start-from",
        type=int,
        default=1,
        help="Starting run number (default: 1)",
    )
    parser.add_argument(
        "--post-submit-delay",
        type=int,
        default=10,
        help="Small delay in seconds after successful submission before next run (default: 10)",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=300,
        help="Timeout in seconds for each job submission (default: 300 = 5 minutes)",
    )

    # Parse known args first to separate launch.py args from tool args
    args, remaining = parser.parse_known_args()

    # Validate run_template format
    if "0x" not in args.run_template:
        print("Error: run_template must contain '0x' placeholder", file=sys.stderr)
        sys.exit(1)

    if not args.run_template.startswith("run="):
        print("Error: run_template must start with 'run='", file=sys.stderr)
        sys.exit(1)

    # Find launch.py script
    repo_root = Path(__file__).parent.parent
    launch_script = repo_root / "devops" / "skypilot" / "launch.py"
    if not launch_script.exists():
        print(f"Error: Could not find launch script at {launch_script}", file=sys.stderr)
        sys.exit(1)

    # Build base command
    base_cmd = [
        "uv",
        "run",
        str(launch_script),
        args.module_path,
    ]

    # Add remaining arguments (like --no-spot --gpus 4)
    base_cmd.extend(remaining)

    # Launch runs sequentially
    for run_num in range(args.start_from, args.start_from + args.num_runs):
        # Format run name with zero-padded number
        run_name = args.run_template.replace("0x", f"{run_num:02d}")
        cmd = base_cmd + [run_name]

        print(f"\n{'=' * 80}")
        print(f"Launching run {run_num}/{args.start_from + args.num_runs - 1}")
        print(f"Run name: {run_name}")
        print(f"Command: {' '.join(cmd)}")
        print(f"{'=' * 80}\n")

        # Execute the command and capture output
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            # Track if we've seen successful submission
            job_submitted = False
            job_id = None
            request_id = None
            start_time = time.time()
            timeout_exceeded = False

            # Read output line by line and print in real-time
            # Use a thread-safe approach to handle timeout
            output_lock = threading.Lock()

            def read_output(proc=process, lock=output_lock):
                nonlocal job_submitted, job_id, request_id
                try:
                    for line in proc.stdout:
                        with lock:
                            print(line, end="")

                            # Check for successful submission indicators
                            if "Submitted sky.jobs.launch request:" in line:
                                job_submitted = True
                                # Extract request ID if possible
                                try:
                                    request_id = line.split("Submitted sky.jobs.launch request:")[1].strip()
                                except IndexError:
                                    pass

                            if "Job ID:" in line:
                                job_submitted = True
                                # Extract job ID if possible
                                try:
                                    job_id = line.split("Job ID:")[1].strip()
                                except IndexError:
                                    pass
                except Exception:
                    pass  # Process may have been terminated

            # Start reading output in a separate thread
            reader_thread = threading.Thread(target=read_output, daemon=True)
            reader_thread.start()

            # Monitor for timeout
            while process.poll() is None:
                elapsed = time.time() - start_time
                if elapsed > args.timeout_seconds:
                    timeout_exceeded = True
                    print(
                        f"\n⏱️  Timeout exceeded ({args.timeout_seconds}s) for run {run_num}",
                        file=sys.stderr,
                    )
                    print("Terminating process...", file=sys.stderr)
                    try:
                        process.terminate()
                        # Give it a moment to terminate gracefully
                        time.sleep(2)
                        if process.poll() is None:
                            process.kill()
                    except Exception as e:
                        print(f"Error terminating process: {e}", file=sys.stderr)
                    break
                time.sleep(0.1)  # Small sleep to avoid busy-waiting

            # Wait for reader thread to finish (with a small timeout)
            reader_thread.join(timeout=1.0)

            # Get final return code
            return_code = process.returncode

            if timeout_exceeded:
                print(
                    f"\n❌ Run {run_num} timed out after {args.timeout_seconds} seconds",
                    file=sys.stderr,
                )
                sys.exit(1)

            if return_code != 0:
                print(f"\n❌ Run {run_num} failed with exit code {return_code}", file=sys.stderr)
                sys.exit(1)

            if not job_submitted:
                print(
                    f"\n⚠️  Warning: Run {run_num} completed but didn't detect job submission confirmation",
                    file=sys.stderr,
                )
                print("Proceeding anyway, but you may want to verify the job was submitted.", file=sys.stderr)

            elapsed_time = time.time() - start_time
            print(f"\n✅ Run {run_num} launched successfully", end="")
            if job_id:
                print(f" (Job ID: {job_id})", end="")
            print(f" (took {elapsed_time:.1f}s)")

        except Exception as e:
            print(f"\n❌ Run {run_num} failed with error: {e}", file=sys.stderr)
            sys.exit(1)

        # Small delay after successful submission before next run (except for the last one)
        if run_num < args.start_from + args.num_runs - 1:
            print(f"\nWaiting {args.post_submit_delay} seconds before next run...")
            time.sleep(args.post_submit_delay)

    print(f"\n✅ Successfully launched {args.num_runs} runs")


if __name__ == "__main__":
    main()
