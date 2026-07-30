from fastapi.testclient import TestClient
from main import app

# Create a TestClient using our FastAPI app
client = TestClient(app)


def test_chat_endpoint_success():
    """
    Test that the /chat endpoint returns a 200 OK status
    and a response containing 'answer' and 'context_used'
    """
    response = client.post(
        "/chat", json={"question": "What planet is the fourth from the sun?"}
    )

    # Assert the request was successful
    assert response.status_code == 200

    # Parse the JSON response
    data = response.json()

    # Assert our expected keys are in the response
    assert "answer" in data
    assert "context_used" in data

    # Assert that the context actually retrieved something about Mars
    assert "Mars" in data["context_used"]


def test_chat_endpoint_empty_question():
    """
    Test how the API handles an empty string for a question.
    (Depending on how you wrote it, it might still return 200 but give a generic answer)
    """
    response = client.post("/chat", json={"question": ""})
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data

def test_chat_stream_endpoint_success():
    """
    Test that the /chat/stream endpoint returns a 200 OK status
    and streams back Server-Sent Events (SSE).
    """
    with client.stream(
        "POST", 
        "/chat/stream", 
        json={"question": "What planet is the fourth from the sun?", "session_id": "test_session"}
    ) as response:
        assert response.status_code == 200
        # Grab the lines to verify it is streaming Server-Sent Events
        lines = list(response.iter_lines())
        assert len(lines) > 0
        
        # Verify the SSE format
        has_data = any(line.startswith("data:") for line in lines)
        assert has_data
