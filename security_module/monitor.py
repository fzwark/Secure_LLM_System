import os
import json
import yaml
import copy
from cores import *
import re, jsonschema
from jsonschema import validate

class Monitor:
    def __init__(self, tools_check=None, tools_config=None, users=None):
        self.label = 'T'

        # Default system prompt for planner 
        self.sys_prompt_planner = SYSTEM_PROMPT_TEMPLATE

        # Default system prompt for executor
        self.sys_prompt_executor = "You are a helpeful assistant!"
            
        # control all tools
        if tools_check == None:
            raise Exception("Unknown tools security check configuration.")
        else:
            self.tools_check = tools_check

        with open(self.tools_check, "r") as f:
            self.tools_check = yaml.safe_load(f)
        
        if tools_config == None:
            raise Exception("Unknown tools configuration.")
        else:
            self.tools_config = tools_config

        with open(self.tools_config, "r") as f:
            self.tools_config = json.load(f)


        # read the user config
        if users == None:
            raise Exception("Unknown users configuration.")
        else:
            self.users = users

        with open(self.users, "r") as f:
            self.user_config = yaml.safe_load(f)


        # memory tool

        self.refs = {}

        # tools for users
        self.users_tools = {}

        self.type_mapping = {
            "string": str,
            "object" : dict,
            "integer" : int,
            "array" : list
        }

    def get_label_user(self, user):
        return self.user_config[user]["label"]
        

    def create_planner(self, label='T', llm=None, sys_prompt=None, tools=None):
        # prepare the tools for the planner based on the user
        if llm == None:
            raise Exception("Empty LLM provided!")
        
        # choose tools
        if sys_prompt == None:
            sys_prompt_planner = self.sys_prompt_planner
        else:
            sys_prompt_planner = sys_prompt
        
        try:
            tools_configuration = json.dumps(tools, indent=4)
            sys_prompt_planner = sys_prompt_planner.format(available_tools=tools_configuration)

        except:
            raise Exception("The format of the system prompt is not correct!")

        planner = Planner(llm=llm, sys_prompt=sys_prompt_planner,label=label)

        return planner
    
    def create_executor(self, llm=None, user=None, sys_prompt=None):
        if user == None:
            raise Exception("Empty user!")
        
        if llm == None:
            raise Exception("Empty LLM provided!")

        label = self.get_label_user(user)

        if sys_prompt == None:
            executor = Executor(llm = llm, label = label, sys_prompt=self.sys_prompt_executor)
        else:
            executor = Executor(llm = llm,  label = label, sys_prompt=sys_prompt)

        return executor
    

    def prepare_context(self, user, llm, planner_label = 'T', sys_prompt_planner=None, sys_prompt_executor=None, tools=None, runnable_tools=None):
        # prepare the tools based on the given user
        available_tool_configs = []
        if tools == None:
            available_tool_configs = self.tools_config
        else:
            available_tool_configs = tools

        planner = self.create_planner(planner_label, llm, sys_prompt=sys_prompt_planner, tools=available_tool_configs)
    
        # prepare the data and the executor based on the given user
        executor = self.create_executor(llm=llm, user=user, sys_prompt=sys_prompt_executor)

        self.users_tools[user] = runnable_tools
 
        return planner, executor
    
    def create_ref(self, user, data, label, ref):
        if user not in self.refs.keys():
            ref_data = {
                ref : {
                        "label" : label,
                        "data" : data
                    }
            }

            self.refs[user] = ref_data

        else:
            self.refs[user][ref] = {
                        "label" : label,
                        "data" : data
                    }

        return ref
    
    def load_ref(self, user, ref):
        return self.refs[user][ref]
    

    def security_check(self, user, dict_generated_plan):
        checked_generated_plan = []
        former_outputs = []
        if dict_generated_plan == []:
            return "[]", "[]"
        for step in dict_generated_plan:
            data = self.load_ref(user, f"Output_{step["Index"]}")
            # check integrity 
            if len(data['label']) == 1:
                if data['label'][0] == 'T':
                    step["Data_output"][-1] = data['data']
                    former_outputs.append(data['data'])
                else:
                    former_outputs.append(step["Data_output"][0])
            else:
                loaded = []
                for idx, item in enumerate(data['label']):
                    if item == 'T':
                        loaded.append(data['data'][idx])
                        former_outputs.append(data['data'][idx])
                
                if loaded == []:
                    loaded = step["Data_output"][0]
                    former_outputs.append(step["Data_output"][0])
        

                step["Data_output"][-1] = loaded

            checked_generated_plan.append(step)

        return json.dumps(checked_generated_plan, indent=4), former_outputs

    def type_check(self, user, step):
        type_step = {}
        try:
            index = step["Index"]
            instruction = step["Instruction"]
            object = step["Object"]
            input = step["Data_input"]
            output = step["Data_output"]
        except:
            return f"ERROR: Wrong syntax for generated plan at current step."


        # syntax check
        if (object != "LLM") and (object not in self.tools_check.keys()):
            return f"ERROR: Wrong object value generation at current step."
        
    
        input_type = "string" if object == "LLM" else "func"
        
        pattern = r"\{\s*\"*Data_output\"*\s*:\s*\d+\s*\}"
        if not isinstance(input, str):
            if input == {'None'}:
                input = 'None'
            input = json.dumps(input, indent=4)

        res = re.findall(pattern, input)
        if res != []:
            if input_type == "string":
                input_type = "string_ref"
            if input_type == "func":
                input_type = "func_ref"
        else:
            if input.lower() == "None".lower():
                if input_type == "string":
                    input_type = "string_none"
                if input_type == "func":
                    input_type = "func_none"
                
        
        # check syntax of reference data
        if input_type == "string_ref" or input_type == "func_ref":
            for data in res:
                pattern_num = r"\d+"
                ref_index = re.findall(pattern_num, data)[0]
                if int(ref_index) >= int(index):
                    return f"ERROR: Incorrect data reference at current step."

        # check the function & args
        if "func" in input_type:
            func = object

            for x in self.tools_config:
                if func == x["name"]:
                    tool_config = x


            # check function
            if func not in self.tools_check.keys():
                return f"ERROR: Incorrect function name generation at current step."
            
            # check args
            try:
                if input == "" or input.lower() == "None".lower() or input.lower() == "Null".lower() or input == "{}":
                    if 'required' in tool_config['parameters'].keys():
                        return f"ERROR: Incorrect parameter syntax at current step. You need to specify at parameters!"
                    args = None
                else:
                    args = eval(input)
            except:
                return f"ERROR: Incorrect parameter syntax at current step."
            
                
            if args != None:
                keys = list(tool_config["parameters"]["properties"].keys())
                for key in args.keys():                        
                    if key not in keys:
                        return f"ERROR: Incorrect parameter keys at current step. Unknown parameter \"{key}\""
                
                required_keys = tool_config["parameters"]["required"]
                for key in required_keys:
                    if key not in args.keys():
                        return f"ERROR: Incorrect parameter keys at current step. You need to specify parameter \"{key}\"."

        
        executable_data_input = []
        if "none" in input_type:
            executable_data_input = "None"
        elif "string" in input_type:
            executable_data_input = input
        elif "func" in input_type:
            executable_data_input = {
                "args" : args
            }

        type_step = {
            "Index" : index,
            "Instruction": instruction,
            "Object_name" : object,
            "Object" : object if object == 'LLM' else self.users_tools[user][object],
            "Object_type" : None if object == 'LLM' else self.tools_check[object]['local_deploy'],
            "Data_input" : executable_data_input,
            "Data_input_type" : input_type,
            "LLM_input_label" : 'T',
            "Data_output" : output
        }

        return type_step


    

    def prepare_data(self, user, step:dict, run_time_plan):
        input_type = step["Data_input_type"]
        input =  step["Data_input"]
        run_time_input = []
        LLM_input_label = 'T'

        if input_type == "string_ref":
            run_time_input = input
            pattern = r"\{\s*\"*Data_output\"*\s*:\s*\d+\s*\}"
            res_ref = re.findall(pattern, input)
            for x in res_ref:
                pattern_num = r"\d+"
                ref_index = re.findall(pattern_num, x)[0]
                reference = run_time_plan[int(ref_index) - 1]["Data_output"][1]
                data = self.load_ref(user, reference)
                run_time_input = run_time_input.replace(x, str(data["data"]))
                if 'U' in data["label"]:
                    LLM_input_label = ' U'

            step["Data_input"] = run_time_input         

        if input_type == "func_ref" or input_type == "func":
            for x in self.tools_config:
                if step["Object_name"] == x["name"]:
                    tool_config = x

            args = input["args"]
            if args == None:
                return step
            
            for item in args:
                data = args[item]

                if isinstance(data, int):
                    args[item] = data
                elif isinstance(data, list):
                    for x in data:
                        pattern = r"\{\s*\"*Data_output\"*\s*:\s*\d+\s*\}"
                        res = re.findall(pattern, str(x))
                        if res != []:
                            pattern_num = r"\d+"
                            ref_index = re.findall(pattern_num, str(x))[0]
                            reference = run_time_plan[int(ref_index) - 1]["Data_output"][1]
                            real_data = self.load_ref(user, reference)
                            args[item][x] = real_data["data"]
                else:
                    pattern = r"\{\s*\"*Data_output\"*\s*:\s*\d+\s*\}"
                    if isinstance(data, dict):
                        data = json.dumps(data)
                    res = re.findall(pattern, data)
                    if res != []:
                        pattern_num = r"\d+"
                        ref_index = re.findall(pattern_num, data)[0]
                        reference = run_time_plan[int(ref_index) - 1]["Data_output"][1]
                        real_data = self.load_ref(user, reference)
                        args[item] = real_data["data"]

                schema = {
                            "properties": tool_config["parameters"]["properties"],
                            "required" : tool_config["parameters"]["required"]
                        }
                try:
                    validate(instance=args, schema=schema)
                except jsonschema.exceptions.ValidationError as e :
                    return f"ERROR: Incorrect parameter type at current step. The value of the parameter \"{e.relative_path[0]}\" is incorrect: {e.message}!"

            step["Data_input"]["args"] = args
        step['LLM_input_label'] = LLM_input_label

        return step
    
    def post_security_label_assign(self, output, step, user):
        # assign the label to the output data
        # currently only support tools used in the paper

        label_output = []
        # tool-LLM check
        if step['Object_name'] == 'LLM':
            label_output = [step['LLM_input_label']]
            return label_output

        # Facility check
        checks = self.tools_check[step['Object_name']]['check']
        return_type = eval(self.tools_check[step['Object_name']]['return_type'])
        configs = self.user_config[user]['trusted']

        if step['Data_input']!= "None":
            args = step['Data_input']['args']

        if checks == "None":
            label_output = ['T']
        
        elif checks['type'] == 'input':
            for item in checks['keys']:
                if list(item.keys())[0] == 'path':
                    path = os.path.join(self.tools_check[step['Object_name']]['dir'], args[item['path']])
                    f = 0
                    for pa in configs['path']:
                        if os.path.samefile(path, pa):
                            f = 1
                            break
                    if  f == 0:
                        label_output.append('U')
                    else:
                        label_output.append('T')

                elif list(item.keys())[0] == 'object':
                    if item['object'] not in configs['object']:
                        label_output.append('U')
                    else:
                        label_output.append('T')
                    
        elif checks['type'] == 'return':
            if return_type == list[dict]:
                for o in output:
                    flag = 1
                    for item in checks['keys']:
                        if list(item.keys())[0] == 'path':
                            path = os.path.join(self.tools_check[step['Object_name']]['dir'], o[item['path']])
                            if  path not in configs['path']:
                                label_output.append('U')
                                flag = 0
                                break
                                
                        elif list(item.keys())[0] == 'object':
                            flag1 = 1
                            for object in configs['object']:
                                if object in o[item['object']]:
                                    flag1 = 0
                                    break

                            if flag1:   
                                label_output.append('U')
                                flag = 0
                                break   
                    
                    if flag:
                        label_output.append('T')     
    
        return label_output
    
    def modify_step(self, user, str_step_original, dict_step_original, runtime_step, output_label, output):
        # store the output
        ref1 = self.create_ref(user, output, output_label, f"Output_{runtime_step["Index"]}")
        runtime_step["Data_output"] = [runtime_step["Data_output"], ref1]

        # modify plan
        filled_str_step_original = copy.deepcopy(str_step_original)
        filled_dict_step_original = copy.deepcopy(dict_step_original)
        index = filled_dict_step_original["Index"]
        ref = '''{{Data_output : {index}}}'''.format(index= index)
        filled_str_step_original["Data_output"] = f"[{filled_str_step_original["Data_output"]}, {ref}]"
        filled_dict_step_original["Data_output"] = [filled_dict_step_original["Data_output"], ref]
      
        return filled_str_step_original, filled_dict_step_original, runtime_step
    

