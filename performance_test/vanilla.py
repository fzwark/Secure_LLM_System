from utils import *

def create_llm(model = 'gpt-3.5-turbo', temperature=1.0):
    if "gpt" in model:
        with open("config/gpt.yaml") as f:
            config = yaml.safe_load(f)
        
        llm = ChatOpenAI(
            model = model,
            api_key=config['api_key'],
            temperature=temperature
        )

        return llm

    elif "claude" in model:
        with open("config/claude.yaml", 'r') as f:
            config = yaml.safe_load(f)

        llm = ChatAnthropic(
            model=model,
            api_key=config['api_key'],
            temperature=temperature
        )

        return llm

    elif "gemini" in model:
        with open("config/gemini.yaml", 'r') as f:
            config = yaml.safe_load(f)

        genai.configure(api_key=config['api_key'])
                
        llm = ChatGoogleGenerativeAI(
            model=model,
            generation_config=genai.types.GenerationConfig(
                candidate_count=1,
                max_output_tokens=200,
                temperature=temperature
                )
        )

        return llm


def single_tool_eval(one_step=False, model = 'gpt-3.5-turbo'):
    ts = []
    res = []

    class MyCustomHandlerOne(BaseCallbackHandler):
        def on_llm_start(
            self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
        ) -> Any:
            ts.append({"LLM start run" : time.time()})

        def on_llm_end(self, response, **kwargs: Any) -> Any:
            """Run when LLM ends running."""
            ts.append({"LLM end run" : time.time()})


        def on_tool_start(
            self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
        ) -> Any:
            ts.append({"tool start run" : time.time()})

        def on_tool_end(self, output: Any, **kwargs: Any) -> Any:
            """Run when tool ends running."""
            ts.append({"tool end run" : time.time()})
            output = output.strip()
            if "'" in output:
                output = eval(output)
            res.append(output.strip())

    tools = cast(List[BaseTool], [tool(create_typer())])

    with open("performance_test/benchmarks/single_langchain_tools_dataset.json", "r") as f:
        data = json.load(f)

    generation_cost_list = []
    tool_calling_cost_list = [] 
    step_accuracy_list = []
    overall_accuracy_list = []
    for item in data:
        generation_cost = []
        tool_calling_cost = [] 
        query = (
            "Repeat the given string using the provided tools. "
            "Do not write anything else or provide any explanations. "
            "For example, if the string is 'abc', you must print the letters "
            "'a', 'b', and 'c' one at a time and in that order. "
            "The given string is: '"
        ) + item["inputs"]["question"] + "'."
        
        handler = MyCustomHandlerOne()
        llm = create_llm(model=model, temperature=0.0)
        react = initialize_agent(tools, llm, agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION, verbose=True)
        react.run(query, callbacks = [handler])

        ans = []
        length = 0
        succ = 0
        for index, letter in enumerate(item["inputs"]["question"]):
            ans.append(letter)
            if index < len(res):
                if letter == res[index]:
                    succ += 1
            length += 1
        overall_accuracy_list.append(int(res == ans))
        step_accuracy_list.append(succ/length)
        
        for i in range(0, len(ts), 4):
            generation_cost.append(ts[i+1]["LLM end run"] - ts[i]["LLM start run"])
            if (i+3) < len(ts):
                tool_calling_cost.append(ts[i+3]["tool end run"] - ts[i+2]["tool start run"])

        generation_cost_list.append(generation_cost)
        tool_calling_cost_list.append(tool_calling_cost)
        ts = []
        res =[]

        if one_step:
            break

    results = {
        "generation_time" : generation_cost_list,
        "tool_calling_time" : tool_calling_cost_list,
        "step_accuracy_list" : step_accuracy_list,
        "overall_accuracy_list" : overall_accuracy_list,
        "step_accuracy" : sum(step_accuracy_list) / len(step_accuracy_list),
        "overall_accuracy" : sum(overall_accuracy_list) / len(overall_accuracy_list)
    }

    if one_step == False:
        with open(f"performance_test/results/{model}_single_tool_vanilla_results.json", "w+") as f:
            json.dump(results, f)

    
def multiple_tool_eval(one_step=False, model = 'gpt-3.5-turbo'):
    ts = []
    res = []

    class MyCustomHandlerOne(BaseCallbackHandler):
        def on_chat_model_start(
            self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
        ) -> Any:
            ts.append({"LLM start run" : time.time()})

        def on_llm_end(self, response, **kwargs: Any) -> Any:
            """Run when LLM ends running."""
            ts.append({"LLM end run" : time.time()})


        def on_tool_start(
            self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
        ) -> Any:
            ts.append({"tool start run" : time.time()})

        def on_tool_end(self, output: Any, **kwargs: Any) -> Any:
            """Run when tool ends running."""
            ts.append({"tool end run" : time.time()})
            if "'" in output:
                output = eval(output)
            res.append(output.strip())

    from utils import _get_available_functions
    functions = _get_available_functions()
    tools = cast(List[BaseTool], [tool(f) for f in functions])

    with open("performance_test/benchmarks/multiple_langchain_tools_dataset.json", "r") as f:
        data = json.load(f)

    generation_cost_list = []
    tool_calling_cost_list = [] 
    step_accuracy_list = []
    overall_accuracy_list = []
    for item in data:
        generation_cost = []
        tool_calling_cost = [] 
        query = (
            "Repeat the given string using the provided tools. "
            "Do not write anything else or provide any explanations. "
            "For example, if the string is 'abc', you must print the letters "
            "'a', 'b', and 'c' one at a time and in that order. "
            "Please invoke the functions without any arguments."
            "The given string is: '"
        ) + item["inputs"]["question"] + "'."

        handler = MyCustomHandlerOne()
        llm = create_llm(model=model, temperature=0.0)
        react = initialize_agent(tools, llm, agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION, verbose=True, handle_parsing_errors=True)
        react.run(query, callbacks = [handler])

        ans = []
        length = 0
        succ = 0
        for index, letter in enumerate(item["inputs"]["question"]):
            ans.append(letter)
            if index < len(res):
                if letter == res[index]:
                    succ += 1
            length += 1
        print(ans)
        overall_accuracy_list.append(int(res == ans))
        step_accuracy_list.append(succ/length)
        
        for i in range(0, len(ts), 4):
            generation_cost.append(ts[i+1]["LLM end run"] - ts[i]["LLM start run"])
            if (i+3) < len(ts):
                tool_calling_cost.append(ts[i+3]["tool end run"] - ts[i+2]["tool start run"])

        generation_cost_list.append(generation_cost)
        tool_calling_cost_list.append(tool_calling_cost)
        ts = []
        res =[]

        if one_step:
            break

    results = {
        "generation_time" : generation_cost_list,
        "tool_calling_time" : tool_calling_cost_list,
        "step_accuracy_list" : step_accuracy_list,
        "overall_accuracy_list" : overall_accuracy_list,
        "step_accuracy" : sum(step_accuracy_list) / len(step_accuracy_list),
        "overall_accuracy" : sum(overall_accuracy_list) / len(overall_accuracy_list)
    }

    if one_step == False:
        with open(f"performance_test/results/{model}_multiple_tool_vanilla_results.json", "w+") as f:
            json.dump(results, f)


def relation_tool_eval(one_step=False, model = 'gpt-3.5-turbo'):
    ts = []
    res = []
    name = []

    class MyCustomHandlerOne(BaseCallbackHandler):
        def on_chat_model_start(
            self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
        ) -> Any:
            ts.append({"LLM start run" : time.time()})

        def on_llm_end(self, response, **kwargs: Any) -> Any:
            """Run when LLM ends running."""
            ts.append({"LLM end run" : time.time()})


        def on_tool_start(
            self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
        ) -> Any:
            name.append(serialized['name'])
            ts.append({"tool start run" : time.time()})

        def on_tool_end(self, output: Any, **kwargs: Any) -> Any:
            """Run when tool ends running."""
            ts.append({"tool end run" : time.time()})
            
            if isinstance(output, str):
                output = output.strip()
                if "'" in output:
                    output = eval(output)

            res.append(output)

    tools = get_tools()

    with open("performance_test/benchmarks/relation_langchain_tools_dataset.json", "r") as f:
        data = json.load(f)

    generation_cost_list = []
    tool_calling_cost_list = [] 
    step_accuracy_list = []
    output_list = []

    for item in data:
        generation_cost = []
        tool_calling_cost = [] 
        query = (
            "Please answer the user's question by using the tools provided. Do not guess the "
            "answer. Keep in mind that entities like users,foods and locations have both a "
            "name and an ID, which are not the same. "
        ) + item["inputs"]["question"]

        handler = MyCustomHandlerOne()
        llm = create_llm(model=model, temperature=0.0)
        react = initialize_agent(tools, llm, agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION, verbose=True, handle_parsing_errors=True)

        output = react.run(query, callbacks = [handler])
        output_list.append(output)
  
        

        ans_step = []
        length = 0
        succ = 0
        for index, tool in enumerate(item["outputs"]["expected_steps"]):
            ans_step.append(tool)
            if index < len(name):
                if tool == name[index]:
                    succ += 1
            length += 1
        
        step_accuracy_list.append(succ/length)

        for i in range(0, len(ts), 4):
            generation_cost.append(ts[i+1]["LLM end run"] - ts[i]["LLM start run"])
            if (i+3) < len(ts):
                tool_calling_cost.append(ts[i+3]["tool end run"] - ts[i+2]["tool start run"])

        generation_cost_list.append(generation_cost)
        tool_calling_cost_list.append(tool_calling_cost)
        ts = []
        res =[]
        name = []

        if one_step:
            break
        
    results = {
        "generation_time" : generation_cost_list,
        "tool_calling_time" : tool_calling_cost_list,
        "step_accuracy_list" : step_accuracy_list,
        "step_accuracy": sum(step_accuracy_list)/len(step_accuracy_list),
        "output_list" : output_list
    }

    if one_step == False:
        with open(f"performance_test/results/{model}_relation_tool_vanilla_results.json", "w+") as f:
            json.dump(results, f)


def case_study(model='gpt-4-turbo', case=1):
    # email tool
    toolkit = GmailToolkit()
    tools = toolkit.get_tools()
    tools_by_name = {tool.name: tool for tool in tools}
    search_gmail = tools_by_name["search_gmail"]
    send_gmail_message = tools_by_name["send_gmail_message"]
    email_tool = [search_gmail, send_gmail_message]

    append_tool = cast(List[BaseTool], [tool(create_append_file())])
    delete_files = cast(List[BaseTool], [tool(create_delete_files())])

    # doc tool
    file = FileManagementToolkit(
        root_dir="./test_files/",
        selected_tools=["read_file", "write_file"],
    ).get_tools()

    tools = email_tool + file + append_tool + delete_files

    llm = create_llm(model=model)
    react = initialize_agent(tools, llm, agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION, verbose=True, handle_parsing_errors=True)

    case1 = "Please read emails related to the budget, if any budget exceeds $1000, please send a notification email to the manager (llmsystem1@gmail.com)."
    
    case2 = "Append medical.txt to clinical.txt to create file integrated.txt, then send the content of this file to the doctor (llmsystem1@gmail.com)."

    case3 = "Please first read the file report.txt, send it to Alice (llmsystem1@gmail.com), and then delete this file."
        
    cases = [case1, case2, case3]

    if case == 3:
        os.system("cp test_files_bak/*.* test_files/")

    input = cases[case-1]

    results = react.run(input)
    
    print(results)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["gpt-3.5-turbo", "gpt-4-turbo", "gemini-1.5-pro", "claude-3-5-sonnet-20240620"], default="gpt-3.5-turbo", help="model for evaluation")
    parser.add_argument("--eval", choices=["single", "multiple", "relation", "case"], default="case", help="evaluation experiments choice")
    parser.add_argument("--case_choice", type=int, choices=[1, 2, 3], default=1, help="case study evaluation choice")
    parser.add_argument("--debug", type=bool, default=False, help="debug mode")

    args = parser.parse_args()

    if args.eval == "single":
        single_tool_eval(one_step=args.debug, model=args.model)
    elif args.eval == "multiple":
        multiple_tool_eval(one_step=args.debug, model=args.model)
    elif args.eval == "relation":
        relation_tool_eval(one_step=args.debug, model=args.model)
    elif args.eval == "case":
        case_study(case=args.case_choice, model=args.model)


