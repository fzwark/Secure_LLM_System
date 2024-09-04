import os, json, time, sys, argparse
from typing import Any, Callable, List, cast, Dict, TypedDict
from langchain.tools import StructuredTool
from langchain_core.tools import ToolException
from langchain_core.utils.function_calling import convert_to_openai_function
from langchain_community.agent_toolkits import FileManagementToolkit
from langchain_community.agent_toolkits import GmailToolkit
from langchain_openai import ChatOpenAI
from langchain.tools import BaseTool, tool
from langchain.agents import AgentType, initialize_agent
from langchain.callbacks.base import BaseCallbackHandler
from langchain_anthropic import ChatAnthropic
import google.generativeai as genai
from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    HarmBlockThreshold,
    HarmCategory,
)

parentddir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
sys.path.append(parentddir)

from model.ChatGPT import *


USER_DATA = [
    # IDs are not consecutive to prevent agents from guessing the ID
    {
        "id": 1,
        "name": "Alice",
        "email": "alice@gmail.com",
        "location": 1,
        "favorite_color": "red",
        "favorite_foods": [1, 2, 3],
    },
    {
        "id": 21,
        "name": "Bob",
        "email": "bob@hotmail.com",
        "location": 2,
        "favorite_color": "orange",
        "favorite_foods": [4, 5, 6],
    },
    {
        "id": 35,
        "name": "Charlie",
        "email": "charlie@yahoo.com",
        "location": 3,
        "favorite_color": "yellow",
        "favorite_foods": [3, 7, 2],
    },
    {
        "id": 41,
        "name": "Donna",
        "email": "donna@example.com",
        "location": 4,
        "favorite_color": "green",
        "favorite_foods": [6, 1, 4],
    },
    {
        "id": 42,
        "name": "Eve",
        "email": "eve@example.org",
        "location": 5,
        "favorite_color": "blue",
        "favorite_foods": [5, 7, 4],
    },
    {
        "id": 43,
        "name": "Frank The Cat",
        "email": "frank.the.cat@langchain.dev",
        "location": 5,
        "favorite_color": "yellow",
        "favorite_foods": [3],
    },
]

# Create a list of JSON data for locations with "current_weather" as a single string
LOCATION_DATA = [
    {
        "id": 1,
        "city": "New York",
        "current_time": "2023-11-14 10:30 AM",
        "current_weather": "Partly Cloudy, Temperature: 68°F",  # Example weather string
    },
    {
        "id": 2,
        "city": "Los Angeles",
        "current_time": "2023-11-14 7:45 AM",
        "current_weather": "Sunny, Temperature: 75°F",  # Example weather string
    },
    {
        "id": 3,
        "city": "Chicago",
        "current_time": "2023-11-14 11:15 AM",
        "current_weather": "Mostly Cloudy, Temperature: 60°F",  # Example weather string
    },
    {
        "id": 4,
        "city": "Houston",
        "current_time": "2023-11-14 12:00 PM",
        "current_weather": "Rainy, Temperature: 55°F",  # Example weather string
    },
    {
        "id": 5,
        "city": "Miami",
        "current_time": "2023-11-14 1:20 PM",
        "current_weather": "Partly Cloudy, Temperature: 80°F",  # Example weather string
    },
]

FOOD_DATA = [
    {
        "id": 1,
        "name": "Pizza",
        "calories": 285,  # Calories per serving
        "allergic_ingredients": ["Gluten", "Dairy"],
    },
    {
        "id": 2,
        "name": "Chocolate",
        "calories": 50,  # Calories per serving
        "allergic_ingredients": ["Milk", "Soy"],
    },
    {
        "id": 3,
        "name": "Sushi",
        "calories": 300,  # Calories per serving
        "allergic_ingredients": ["Fish", "Soy"],
    },
    {
        "id": 4,
        "name": "Burger",
        "calories": 350,  # Calories per serving
        "allergic_ingredients": ["Gluten", "Dairy"],
    },
    {
        "id": 5,
        "name": "Ice Cream",
        "calories": 200,  # Calories per serving
        "allergic_ingredients": ["Dairy"],
    },
    {
        "id": 6,
        "name": "Pasta",
        "calories": 180,  # Calories per serving
        "allergic_ingredients": ["Gluten"],
    },
    {
        "id": 7,
        "name": "Salad",
        "calories": 50,  # Calories per serving
        "allergic_ingredients": [],
    },
]


class SearchHit(TypedDict, total=False):
    """A search hit."""

    id: str

def _similarity_search(data: List[dict], query: str, key: str) -> List[SearchHit]:
    """Return a list of data that matches the given query.

    Similarity score is jaccard similarity based on the number of shared
    characters between the query and the data.

    Args:
        data: The data to search.
        query: The query to search for.
        key: The key to search in.

    Returns:
        The list of matching data.
    """

    def _score_function(x: str) -> float:
        """Calculate the similarity score between the query and the given string."""
        return len(set(x) & set(query)) / len(set(x) | set(query))

    re_ranked_data = sorted(data, key=lambda x: _score_function(x[key]), reverse=True)
    return [{"id": d["id"], key: d[key]} for d in re_ranked_data]


def _get_user(id: int) -> dict:
    """Find the user with the given user ID.

    Args:
        id: The user's ID.

    Returns:
        The user's data.
    """
    if isinstance(id, str):
        id = eval(id)
    for user in USER_DATA:
        if user["id"] == id:
            return user
    raise ToolException(f"User ID {id} cannot be resolved")


def _get_location(id: int) -> dict:
    """Find the location with the given location ID.

    Args:
        id: The location's ID.

    Returns:
        The location's data.
    """
    if isinstance(id, str):
        id = eval(id)
    for location in LOCATION_DATA:
        if location["id"] == id:
            return location
    raise ToolException(f"Location ID {id} cannot be resolved")


def _get_food(food_id: int) -> dict:
    """Find the food with the given food ID.

    Args:
        food_id: The food's ID.

    Returns:
        The food's data.
    """
    if isinstance(food_id, str):
        food_id = eval(food_id)
    for food in FOOD_DATA:
        if food["id"] == food_id:
            return food
    raise ToolException(f"Food ID {food_id} cannot be resolved")


def get_available_functions() -> List[Callable]:
    """Get all the available functions."""

    def get_user_name(user_id: int) -> str:
        """Get the name of the user with the given user ID.

        Args:
            user_id: The user's ID.

        Returns:
            The user's name.
        """
        return _get_user(user_id)["name"]

    def list_user_ids() -> List[str]:
        """List all the user IDs."""
        return [user["id"] for user in USER_DATA]

    def find_users_by_name(name: str) -> List[SearchHit]:
        """Find users with the given name.

        Args:
            name: The name to search for.

        Returns:
            The list of matching users.
        """
        return _similarity_search(USER_DATA, name, "name")

    def find_locations_by_name(city: str) -> List[SearchHit]:
        """Find locations with the given city name."""
        return _similarity_search(LOCATION_DATA, city, "city")

    def find_foods_by_name(food: str) -> List[SearchHit]:
        """Find foods with the given name."""
        return _similarity_search(FOOD_DATA, food, "name")

    def get_user_email(user_id: int) -> str:
        """Get the email of the user with the given user ID.

        Args:
            user_id: The user's ID.

        Returns:
            The user's email.
        """
        return _get_user(user_id)["email"]

    def get_user_location(user_id: int) -> int:
        """Get the location ID of the user with the given user ID.

        Args:
            user_id: The user's ID.

        Returns:
            The user's location ID.
        """
        return _get_user(user_id)["location"]

    def get_user_favorite_color(user_id: int) -> str:
        """Get the favorite color of the user with the given user ID.

        Args:
            user_id: The user's ID.

        Returns:
            The user's favorite color.
        """
        return _get_user(user_id)["favorite_color"]

    def get_user_favorite_foods(user_id: int) -> List[int]:
        """Get the list of favorite foods of the user with the given user ID.

        Args:
            user_id: The user's ID.

        Returns:
            The list of favorite foods.
        """
        return _get_user(user_id)["favorite_foods"]

    def get_weather_at_location(location_id: int) -> str:
        """Get the current weather at the location with the given location ID.

        Args:
            location_id: The location's ID.

        Returns:
            The current weather at the location.
        """
        return _get_location(location_id)["current_weather"]

    def get_city_for_location(location_id: int) -> str:
        """Get the city for the location with the given location ID.

        Args:
            location_id: The location's ID.

        Returns:
            The city name for the location.
        """
        return _get_location(location_id)["city"]

    def get_current_time_for_location(location_id: int) -> str:
        """Get the current time for the location with the given location ID.

        Args:
            location_id: The location's ID.

        Returns:
            The current time for the location.
        """
        return _get_location(location_id)["current_time"]

    def get_current_weather_for_location(location_id: int) -> str:
        """Get the current weather for the location with the given location ID.

        Args:
            location_id: The location's ID.

        Returns:
            The current weather for the location.
        """
        return _get_location(location_id)["current_weather"]

    def get_food_name(food_id: int) -> str:
        """Get the name of the food with the given food ID.

        Args:
            food_id: The food's ID.

        Returns:
            The name of the food.
        """
        return _get_food(food_id)["name"]

    def get_food_calories(food_id: int) -> int:
        """Get the calories per serving for the food with the given food ID.

        Args:
            food_id: The food's ID.

        Returns:
            The calories per serving of the food.
        """
        return _get_food(food_id)["calories"]

    def get_food_allergic_ingredients(food_id: int) -> List[str]:
        """Get the list of allergic ingredients for the food with the given food ID.

        Args:
            food_id: The food's ID.

        Returns:
            The list of allergic ingredients.
        """
        return _get_food(food_id)["allergic_ingredients"]

    def get_current_user_id() -> int:
        """Get the current user's ID.

        Returns:
            The current user's ID.
        """
        return 35

    # Get all the functions defined in the scope of this function
    functions = [f for f in locals().values() if callable(f)]
    return functions


def get_tools() -> List[StructuredTool]:
    """Get all the available tools."""
    functions = get_available_functions()
    return [StructuredTool.from_function(f, handle_tool_error=True) for f in functions]


def create_typer() -> Callable[[str], str]:
    """Create a function that types the given letter."""

    def type_letter(letter: str) -> str:
        """Print the given letter on the paper."""
        return letter

    return type_letter


def create_delete_files() -> Callable[[str], str]:
    """Create a function that deletes the target file."""

    def delete_file(file_path : str) -> str:
        """Delete file in the current dir.

        Args:
            file_path: the name of the target file to delete 

        Returns:
            The result of the file delete operation
        """
        try:
            os.system(f"rm test_files/{file_path}")
            return "Successfully deleted"
        except:
            return "Failed to delete"

    return delete_file


def create_append_file() -> Callable[[str, str, str], str]:
    """Create a function that appends two files."""

    def append_file(source_file1: str, source_file2: str, output_file3: str) -> str:
        """Append two files to create a new file.

        Args:
            source_file1: the name of the first source file to append 
            source_file2: the name of the second source file to append 
            output_file3: the name of created output file 

        Returns:
            The result of the append operation
        """

        try:
            with open(f"test_files/{source_file1}", "r") as f:
                data1 = f.read()
            with open(f"test_files/{source_file2}", "r") as f:
                data2 = f.read()
            with open(f"test_files/{output_file3}", "w+") as f:
                f.write(data2 + "\n" + data1)

            return f"Successfully append files and create file {output_file3}!"
        except:
            return "Failed to append files!"

    return append_file

def _create_typing_func(letter: str) -> Callable[[], str]:
    """Create a function that types the given letter."""

    def func() -> str:
        return letter

    func.__doc__ = f'Run to Type the letter "{letter}".'
    func.__name__ = letter
    return func


def _get_available_functions() -> List[Callable]:
    """Get all the available functions."""
    return [
        _create_typing_func(letter) for letter in "abcdefghijklmnopqrstuvwxyz"
    ]