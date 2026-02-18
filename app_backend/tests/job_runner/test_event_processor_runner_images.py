from metta.app_backend.job_runner.event_processor import _get_runner_images_from_event


def test_get_runner_images_from_event_extracts_image_and_id() -> None:
    event_data = {
        "object": {
            "status": {
                "containerStatuses": [
                    {
                        "image": "ghcr.io/metta-ai/episode-runner:compat-v0.5",
                        "imageID": "ghcr.io/metta-ai/episode-runner@sha256:abc123",
                    }
                ]
            }
        }
    }

    runner_image, runner_image_id = _get_runner_images_from_event(event_data)

    assert runner_image == "ghcr.io/metta-ai/episode-runner:compat-v0.5"
    assert runner_image_id == "ghcr.io/metta-ai/episode-runner@sha256:abc123"


def test_get_runner_images_from_event_handles_missing_status() -> None:
    runner_image, runner_image_id = _get_runner_images_from_event({"object": {"status": {}}})

    assert runner_image is None
    assert runner_image_id is None
