"""ZeroMQ REP server for the Trip Cost Estimate microservice.

Listens for JSON trip cost requests on a ZeroMQ REP socket and replies with
itemized fuel cost, parking fee, entrance fee, and total cost (or a structured
error message).
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from typing import Any

from calculator import handle_raw_message

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5558

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("trip_cost_service")


def process_one_message(socket: Any) -> bool:
    """Receive one ZeroMQ message, compute the response, and send it back.

    Returns:
        True if a message was processed, False if a poll/timeout occurred.
    """
    raw_request = socket.recv()
    raw_response = handle_raw_message(raw_request)
    socket.send(raw_response)
    return True


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Start the ZeroMQ REP server and handle requests until interrupted."""
    try:
        import zmq
    except ImportError as exc:
        raise RuntimeError(
            "pyzmq is required to run the server. Install it with: pip install -r requirements.txt"
        ) from exc

    endpoint = f"tcp://{host}:{port}"
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.bind(endpoint)

    running = True

    def _shutdown_handler(signum: int, _frame: Any) -> None:
        nonlocal running
        logger.info("Received signal %s; shutting down Trip Cost Estimate service...", signum)
        running = False

    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)

    poller = zmq.Poller()
    poller.register(socket, zmq.POLLIN)

    logger.info("Trip Cost Estimate microservice listening on %s", endpoint)

    try:
        while running:
            events = dict(poller.poll(timeout=250))
            if socket in events:
                try:
                    process_one_message(socket)
                except Exception:
                    logger.exception("Unexpected error while handling request")
                    socket.send_json(
                        {
                            "status": "error",
                            "error": "Internal service error while processing request.",
                        }
                    )
    finally:
        socket.close(linger=0)
        context.term()
        logger.info("Trip Cost Estimate microservice stopped.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments with environment variable fallbacks."""
    parser = argparse.ArgumentParser(
        description="Run the Trip Cost Estimate ZeroMQ REP microservice."
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("TRIP_COST_HOST", DEFAULT_HOST),
        help=f"Host interface to bind (default: {DEFAULT_HOST}).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("TRIP_COST_PORT", str(DEFAULT_PORT))),
        help=f"TCP port to bind (default: {DEFAULT_PORT}).",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    try:
        run_server(host=args.host, port=args.port)
    except RuntimeError as err:
        logger.error("%s", err)
        sys.exit(1)
