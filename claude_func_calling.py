from anthropic import Anthropic
import os
import re
from dotenv import load_dotenv
import wikipedia
import yfinance as yf
import xml.etree.ElementTree as ET

load_dotenv()
client = Anthropic(api_key=os.environ.get("ANTHROPIC"))
MODEL_NAME = "claude-3-opus-20240229"

question = input("Ask Claude: ")
multiplication_message = {
    "role": "user", 
    "content": question
}

# Claude accepts in this special format    
def construct_format_tool_for_claude_prompt(names, descriptions, parameter_lists):
    num_tools = len(names)
    constructed_prompts = ""
    for i in range(num_tools):
        name = names[i]
        description = descriptions[i]
        parameters = parameter_lists[i]
        constructed_prompt = (
            "<tool_description>\n"
                "<tool_name>"
                    f"{name}\n"
                "</tool_name>\n"
                
                "<description>\n"
                    f"{description}\n"
                "</description>\n"
                
                "<parameters>\n"
                    f"{construct_format_parameters_prompt(parameters)}\n"
                "</parameters>\n"
            "</tool_description>"
        )
        constructed_prompts += constructed_prompt + "\n"
    return constructed_prompts

# Claude accepts in this special format    
def construct_format_parameters_prompt(parameters):
    constructed_prompt = "\n".join(f"<parameter>\n<name>{parameter['name']}</name>\n<type>{parameter['type']}</type>\n<description>{parameter['description']}</description>\n</parameter>" for parameter in parameters)

    return constructed_prompt

# Define custom functions in here
# each tool must have name, description and parameters matched with function definition
tool1_name = "stock_price"
tool1_description = """Learn stock price of any company using Yahoo Finance"""
tool1_parameters = [
    {
        "name": "stock_name",
        "type": "str",
        "description": "The name of the company for which the user wants to retrieve the stock price."
    }
]
def stock_price(stock_name: str):
    stock_data = yf.Ticker(stock_name)
    stock_price = stock_data.history(period='1d')['Close'].iloc[-1]
    return stock_price

tool2_name = "wikipedia_search"
tool2_description = """Searches Wikipedia based on user input"""
tool2_parameters = [
    {
        "name": "user_input",
        "type": "str",
        "description": "The user input that the user wants to search Wikipedia for."
    }
]
def wikipedia_search(user_input: str):
    """The user input that the user wants to search Wikipedia for."""
    return wikipedia.search(user_input)


names = [tool1_name, tool2_name]
descriptions = [tool1_description, tool2_description]
parameters = [tool1_parameters, tool2_parameters]
tool = construct_format_tool_for_claude_prompt(names, descriptions, parameters)

# Claude accepts in this special format    
def construct_tool_use_system_prompt(tools):
    tool_use_system_prompt = (
        "In this environment you have access to a set of tools you can use to answer the user's question.\n"
        "\n"
        "You may call them like this:\n"
        "<function_calls>\n"
        "<invoke>\n"
        "<tool_name>$TOOL_NAME</tool_name>\n"
        "<parameters>\n"
        "<$PARAMETER_NAME>$PARAMETER_VALUE</$PARAMETER_NAME>\n"
        "...\n"
        "</parameters>\n"
        "</invoke>\n"
        "</function_calls>\n"
        "\n"
        "Here are the tools available:\n"
        "<tools>\n"
        + '\n'.join([tool for tool in tools]) +
        "\n</tools>"
    )
    return tool_use_system_prompt


system_prompt = construct_tool_use_system_prompt([tool])

function_calling_message = client.messages.create(
    model=MODEL_NAME,
    max_tokens=1024,
    messages=[multiplication_message],
    system=system_prompt,
    stop_sequences=["\nHuman:", "\nAssistant", "</function_calls>"]
).content[0].text
#print(function_calling_message) #! Here we print the XML tree

# add '</function_calls>', since we added it as 'stop_sequences'
# XML Tree will no longer have it
function_calling_message += '</function_calls>'
xml_pattern = r'<function_calls>.*?</function_calls>'
xml_parts = re.findall(xml_pattern, function_calling_message, re.DOTALL)  # handle thought texts
    
for xml_part in xml_parts:
    # Parse the XML
    root = ET.fromstring(xml_part)
    
    # Find the tool name and input
    tool_name = root.find('.//tool_name').text

# Call functions
if tool_name == "wikipedia_search":
    inp = root.find('.//user_input').text
    result = wikipedia_search(inp)
elif tool_name == "stock_price":
    inp = root.find('.//stock_name').text
    result = stock_price(inp)
    
def construct_successful_function_run_injection_prompt(invoke_results):
    constructed_prompt = (
        "<function_results>\n"
        + '\n'.join(
            f"<result>\n<tool_name>{res['tool_name']}</tool_name>\n<stdout>\n{res['tool_result']}\n</stdout>\n</result>" 
            for res in invoke_results
        ) + "\n</function_results>"
    )
    
    return constructed_prompt

formatted_results = [{
    'tool_name': tool_name,
    'tool_result': result
}]

function_results = construct_successful_function_run_injection_prompt(formatted_results)

partial_assistant_message = function_calling_message + "</function_calls>" + function_results # concatinate full answer

final_message = client.messages.create(
    model=MODEL_NAME,
    max_tokens=1024,
    messages=[
        multiplication_message,
        {
            "role":"assistant",
            "content":partial_assistant_message
        }
    ],
    system=system_prompt
).content[0].text
print(partial_assistant_message+final_message) # print as assistant