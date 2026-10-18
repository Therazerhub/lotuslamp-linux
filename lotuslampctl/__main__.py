"""Entry point: python -m lotuslampctl"""
import logging
import os

import uvicorn


def main():
    logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"),
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    port = int(os.environ.get("PORT", "8321"))
    uvicorn.run("lotuslampctl.server:app", host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
