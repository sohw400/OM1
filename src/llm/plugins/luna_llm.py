import json
import logging
import time
import typing as T

import requests
from pydantic import BaseModel

from llm import LLM, LLMConfig

R = T.TypeVar("R", bound=BaseModel)


class LunaLLM(LLM[R]):
    """
    An Luna-based Language Learning Model implementation.

    This class implements the LLM interface for DeepSeek's conversation models, handling
    configuration, authentication, and async API communication.

    Parameters
    ----------
    output_model : Type[R]
        A Pydantic BaseModel subclass defining the expected response structure.
    config : LLMConfig, optional
        Configuration object containing API settings. If not provided, defaults
        will be used.
    """

    def __init__(self, output_model: T.Type[R], config: T.Optional[LLMConfig] = None):
        """
        Initialize the Luna LLM instance.

        Parameters
        ----------
        output_model : Type[R]
            Pydantic model class for response validation.
        config : LLMConfig, optional
            Configuration settings for the LLM.
        """
        super().__init__(output_model, config)

        self._config.base_url = (
            config.base_url
            or "http://ec2-13-236-94-100.ap-southeast-2.compute.amazonaws.com/api/v1/text/chat"
        )

        if config.api_key is None or config.api_key == "":
            raise ValueError("config file missing api_key")

    async def ask(self, prompt: str) -> R | None:
        """
        Send a prompt to the Luna API and get a structured response.

        Parameters
        ----------
        prompt : str
            The input prompt to send to the model.

        Returns
        -------
        R or None
            Parsed response matching the output_model structure, or None if
            parsing fails.
        """
        try:
            logging.debug(f"Luna LLM input: {prompt}")
            self.io_provider.llm_start_time = time.time()
            self.io_provider.set_llm_prompt(prompt)

            text = (
                prompt
                + "\n"
                + f"You must respond with valid JSON matching this schema: {self._output_model.model_json_schema()}"
            )

            response = requests.post(
                url=self._config.base_url,
                headers={
                    "Authorization": f"Bearer {self._config.api_key}",
                    "Content-Type": "application/json",
                },
                json={"text": text, "messageHistory": []},
            )

            if response.status_code != 200:
                logging.error(f"LLM response error: {response.text}")
                return None

            parsed_response = json.loads(response.text)
            self.io_provider.llm_end_time = time.time()

            try:
                parsed_response = self._output_model.model_validate_json(
                    parsed_response.get("text", {})
                )
                logging.debug(f"Luna LLM output: {parsed_response}")
                return parsed_response
            except Exception as e:
                logging.error(f"Error parsing response: {e}")
                return None
        except Exception as e:
            logging.error(f"Error asking LLM: {e}")
            return None
