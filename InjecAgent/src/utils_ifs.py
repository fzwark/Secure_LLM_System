import os
import json
import yaml
import copy
from cores import *
import re


class Monitor:
    def __init__(self, users=None):
        self.label = 'T'

        # Default system prompt for planner 
        self.sys_prompt_planner = SYSTEM_PROMPT_TEMPLATE

        # Default system prompt for executor
        self.sys_prompt_executor = "You are a helpeful assistant!"
            

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
            "array" : list,
            "boolean" : bool,
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
    

    def prepare_context(self, user, llm, planner_label = 'T', sys_prompt_planner=None, tools=None, runnable_tools=None):
        # prepare the tools based on the given user
        available_tool_configs = []
        if tools != None:
            available_tool_configs = tools
            self.tools_config = tools

        else:
            raise Exception("needs tool configs to evaluate InjecAgent")

        planner = self.create_planner(planner_label, llm, sys_prompt=sys_prompt_planner, tools=available_tool_configs)


        self.users_tools[user] = runnable_tools
 
        return planner
    
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
    

    def security_check(self, user, dict_generated_plan, previous_outputs):
        checked_generated_plan = []
        former_outputs = []
        if dict_generated_plan == []:
            return "[]", "[]"        
        for idxx, step in enumerate(dict_generated_plan):
            data = previous_outputs[idxx]
            # check integrity 
            self.create_ref(user, data['data'], data['label'], f"Output_{idxx + 1}")

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
        func_names = []
        for x in self.tools_config:
            func_names.append(x['name'])
        if (object != "LLM") and object not in func_names:
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
            if func not in func_names:
                return f"ERROR: Incorrect function name generation at current step."
            
            # check args
            try:
                if input == "" or input.lower() == "None".lower() or input.lower() == "Null".lower() or input == "{}":
                    f = 0
                    for key in tool_config['parameters']:
                        if key['required'] == True:
                            f = 1
                            break
                    if f:
                        return f"ERROR: Incorrect parameter syntax at current step. You need to specify at parameters!"
                    
                    args = None
                else:
                    args = eval(input)
            except:
                return f"ERROR: Incorrect parameter syntax at current step."
            
                
            if args != None:
                keys_list = tool_config["parameters"]
                keys = []
                required_keys = []
                for key in keys_list:
                    keys.append(key['name'])
                    if key['required'] == True:
                        required_keys.append(key['name'])
                
                for key in args.keys():                        
                    if key not in keys:
                        return f"ERROR: Incorrect parameter keys at current step. Unknown parameter \"{key}\""
                
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
                reference = f"Output_{ref_index}"
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
                            # reference = run_time_plan[int(ref_index) - 1]["Data_output"][1]
                            reference = f"Output_{ref_index}"
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
                        reference = f"Output_{ref_index}"
                        real_data = self.load_ref(user, reference)
                        args[item] = real_data["data"]

                for key in tool_config["parameters"]:
                    if item == key['name']:
                        type = key['type']
                        flag = 1
                        if type == "number":
                            if (isinstance(args[item], int) == 0) and (isinstance(args[item], float) == 0):
                                flag = 0

                        else:
                            if isinstance(args[item], self.type_mapping[type]) == 0:
                                flag = 0

                        if flag == 0:
                            return f"ERROR: Incorrect parameter keys at current step. The type of parameter \"{item}\" in function {step["Object_name"]} should be \"{type}\"!"

            
            step["Data_input"]["args"] = args
        step['LLM_input_label'] = LLM_input_label

        return step
    
 
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
    

