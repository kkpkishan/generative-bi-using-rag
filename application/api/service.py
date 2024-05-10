import json
import os
from typing import Union
from dotenv import load_dotenv
import logging

from nlq.business.connection import ConnectionManagement
from nlq.business.nlq_chain import NLQChain
from nlq.business.profile import ProfileManagement
from nlq.business.vector_store import VectorStore
from utils.apis import get_sql_result_tool
from utils.database import get_db_url_dialect
from nlq.business.suggested_question import SuggestedQuestionManagement as sqm
from utils.llm import text_to_sql, get_query_intent, create_vector_embedding_with_sagemaker, \
    sagemaker_to_sql, sagemaker_to_explain, knowledge_search, get_agent_cot_task, data_analyse_tool, \
    generate_suggested_question, data_visualization
from utils.opensearch import get_retrieve_opensearch
from utils.text_search import normal_text_search, agent_text_search
from .schemas import Question, Answer, Example, Option, SQLSearchResult, AgentSearchResult, KnowledgeSearchResult, \
    TaskSQLSearchResult
from .exception_handler import BizException
from utils.constant import BEDROCK_MODEL_IDS, ACTIVE_PROMPT_NAME
from .enum import ErrorEnum

logger = logging.getLogger(__name__)

load_dotenv()
# load config.json as dictionary
with open(os.path.join(os.getcwd(), 'config_files', '1_config.json')) as f:
    env_vars = json.load(f)
opensearch_config = env_vars['data_sources']['shopping_guide']['opensearch']
for key in opensearch_config:
    opensearch_config[key] = os.getenv(opensearch_config[key].replace('$', ''))
datasource_profile = {}
for i, v in env_vars['data_sources'].items():
    datasource_profile[i] = v
all_profiles = ProfileManagement.get_all_profiles_with_info()
all_profiles.update(datasource_profile)


def get_option() -> Option:
    option = Option(
        data_profiles=all_profiles.keys(),
        bedrock_model_ids=BEDROCK_MODEL_IDS,
    )
    return option


def __process_nlq_chain(question: Question) -> NLQChain:
    current_nlq_chain = NLQChain(question.profile_name)

    current_nlq_chain.set_question(question.keywords)
    retrieve_result = []
    if not current_nlq_chain.get_retrieve_samples():
        if question.use_rag:
            logger.info(f'try to get retrieve samples from open search')
            logger.info('Retrieving samples...')
            try:
                # HACK: always use first opensearch
                selected_profile = "shopping_guide"

                logger.info(question.keywords)
                embedding_endpoint = os.getenv('SAGEMAKER_ENDPOINT_EMBEDDING', '')
                if embedding_endpoint:
                    records_with_embedding = create_vector_embedding_with_sagemaker(
                        embedding_endpoint,
                        question.keywords,
                        index_name=env_vars['data_sources'][selected_profile]['opensearch']['index_name'])
                else:
                    # records_with_embedding = create_vector_embedding_with_bedrock(
                    #     question.keywords,
                    #     index_name=env_vars['data_sources'][selected_profile]['opensearch']['index_name'])
                    pass
                logger.info(env_vars['data_sources'][selected_profile]['opensearch']['index_name'])

                retrieve_result = get_retrieve_opensearch(env_vars, current_nlq_chain.get_question(), "query",
                                                          selected_profile, 3, 0.5)
                current_nlq_chain.set_retrieve_samples(retrieve_result)
            except Exception as e:
                logger.exception(e)
                logger.info(f"Failed to retrieve Q/A from OpenSearch: {str(e)}")
                retrieve_result = []
                selected_profile = question.profile_name
    else:
        logger.info(f'get retrieve samples from memory: {len(current_nlq_chain.get_retrieve_samples())}')

    return current_nlq_chain


def verify_parameters(question: Question):
    if question.bedrock_model_id not in BEDROCK_MODEL_IDS:
        raise BizException(ErrorEnum.INVAILD_BEDROCK_MODEL_ID)


def get_example(current_nlq_chain: NLQChain) -> list[Example]:
    examples = []
    for example in current_nlq_chain.get_retrieve_samples():
        examples.append(Example(
            score=example['_score'],
            question=example['_source']['text'],
            answer=example['_source']['sql'].strip()
        )
        )
    return examples


def get_result_from_llm(question: Question, current_nlq_chain: NLQChain, with_response_stream=False) -> Union[
    str, dict]:
    logger.info('try to get generated sql from LLM')

    entity_slot_retrieve = []
    database_profile = all_profiles[question.profile_name]
    if question.intent_ner_recognition:
        intent_response = get_query_intent(question.bedrock_model_id, question.keywords, database_profile['prompt_map'])
        intent = intent_response.get("intent", "normal_search")
        if intent == "reject_search":
            raise BizException(ErrorEnum.NOT_SUPPORTED)
        entity_slot = intent_response.get("slot", [])
        if entity_slot:
            for each_entity in entity_slot:
                entity_retrieve = get_retrieve_opensearch(env_vars, each_entity, "ner", question.profile_name, 1, 0.7)
                if entity_retrieve:
                    entity_slot_retrieve.extend(entity_retrieve)

    # Whether Retrieving Few Shots from Database
    logger.info('Sending request...')
    # fix db url is Empty
    if database_profile['db_url'] == '':
        conn_name = database_profile['conn_name']
        db_url = ConnectionManagement.get_db_url_by_name(conn_name)
        database_profile['db_url'] = db_url

    sql_endpoint = os.getenv('SAGEMAKER_ENDPOINT_SQL', '')
    if sql_endpoint:
        response = sagemaker_to_sql(database_profile['tables_info'],
                                    database_profile['hints'],
                                    question.keywords,
                                    endpoint_name=sql_endpoint,
                                    sql_examples=current_nlq_chain.get_retrieve_samples(),
                                    ner_example=entity_slot_retrieve,
                                    dialect=get_db_url_dialect(database_profile['db_url']),
                                    model_provider=None,
                                    with_response_stream=with_response_stream, )  # This does not support streaming
    else:
        response = text_to_sql(database_profile['tables_info'],
                               database_profile['hints'],
                               database_profile['prompt_map'],
                               question.keywords,
                               model_id=question.bedrock_model_id,
                               sql_examples=current_nlq_chain.get_retrieve_samples(),
                               ner_example=entity_slot_retrieve,
                               dialect=get_db_url_dialect(database_profile['db_url']),
                               model_provider=None,
                               with_response_stream=with_response_stream, )
    return response


def ask(question: Question) -> Answer:
    logger.debug(question)
    verify_parameters(question)

    intent_ner_recognition_flag = question.intent_ner_recognition_flag
    agent_cot_flag = question.agent_cot_flag

    model_type = question.bedrock_model_id
    search_box = question.query
    selected_profile = question.profile_name
    use_rag_flag = question.use_rag_flag
    explain_gen_process_flag = question.explain_gen_process_flag
    gen_suggested_question_flag = question.gen_suggested_question_flag


    reject_intent_flag = False
    search_intent_flag = False
    agent_intent_flag = False
    knowledge_search_flag = False

    agent_search_result = []
    normal_search_result = None

    filter_deep_dive_sql_result = []

    all_profiles = ProfileManagement.get_all_profiles_with_info()
    database_profile = all_profiles[selected_profile]

    current_nlq_chain = NLQChain(selected_profile)

    sql_search_result = SQLSearchResult(sql_data=[], sql="", data_show_type="table",
                                        sql_gen_process="",
                                        data_analyse="")

    agent_search_response = AgentSearchResult(agent_summary="", agent_sql_search_result=[], sub_search_task=[])

    knowledge_search_result = KnowledgeSearchResult(knowledge_response="")

    agent_sql_search_result = []

    generate_suggested_question_list = []

    if database_profile['db_url'] == '':
        conn_name = database_profile['conn_name']
        db_url = ConnectionManagement.get_db_url_by_name(conn_name)
        database_profile['db_url'] = db_url
        database_profile['db_type'] = ConnectionManagement.get_db_type_by_name(conn_name)
    prompt_map = database_profile['prompt_map']


    # Control subsequent logic through flag bits
    # There are 4 main intentions, rejection, query, thought chain, knowledge question and answer
    if intent_ner_recognition_flag:
        intent_response = get_query_intent(model_type, search_box, prompt_map)
        intent = intent_response.get("intent", "normal_search")
        entity_slot = intent_response.get("slot", [])
        if intent == "reject_search":
            reject_intent_flag = True
            search_intent_flag = False
        elif intent == "agent_search":
            agent_intent_flag = True
            if agent_cot_flag:
                search_intent_flag = False
            else:
                search_intent_flag = True
                agent_intent_flag = False
        elif intent == "knowledge_search":
            knowledge_search_flag = True
            search_intent_flag = False
            agent_intent_flag = False
        else:
            search_intent_flag = True
    else:
        search_intent_flag = True

    if reject_intent_flag:
        answer = Answer(query=search_box, query_intent="reject_search", knowledge_search_result=knowledge_search_result,
                        sql_search_result=sql_search_result, agent_search_result=agent_search_response,
                        suggested_question=[])
        return answer
    elif search_intent_flag:
        normal_search_result = normal_text_search(search_box, model_type,
                                                  database_profile,
                                                  entity_slot, env_vars,
                                                  selected_profile, use_rag_flag)
    elif knowledge_search_flag:
        response = knowledge_search(search_box=search_box, model_id=model_type, prompt_map=prompt_map)

        knowledge_search_result.knowledge_response = response
        answer = Answer(query=search_box, query_intent="knowledge_search",
                        knowledge_search_result=knowledge_search_result,
                        sql_search_result=sql_search_result, agent_search_result=agent_search_response,
                        suggested_question=[])
        return answer

    else:
        agent_cot_retrieve = get_retrieve_opensearch(env_vars, search_box, "agent",
                                                     selected_profile, 2, 0.5)
        agent_cot_task_result = get_agent_cot_task(model_type, prompt_map, search_box,
                                                   database_profile['tables_info'],
                                                   agent_cot_retrieve)

        agent_search_result = agent_text_search(search_box, model_type,
                                                database_profile,
                                                entity_slot, env_vars,
                                                selected_profile, use_rag_flag, agent_cot_task_result)

    if gen_suggested_question_flag and (search_intent_flag or agent_intent_flag):
        active_prompt = sqm.get_prompt_by_name(ACTIVE_PROMPT_NAME).prompt
        generated_sq = generate_suggested_question(prompt_map, search_box, model_id=model_type)
        split_strings = generated_sq.split("[generate]")
        generate_suggested_question_list = [s.strip() for s in split_strings if s.strip()]


    
    # Connect to the database, execute SQL, record and display history
    if search_intent_flag:
        if normal_search_result.sql != "":
            current_nlq_chain.set_generated_sql(normal_search_result.sql)
            sql_search_result.sql = normal_search_result.sql
            current_nlq_chain.set_generated_sql_response(normal_search_result.response)
            if explain_gen_process_flag:
                sql_search_result.sql_gen_process = current_nlq_chain.get_generated_sql_explain()
        else:
            sql_search_result.sql = "-1"

        search_intent_result = get_sql_result_tool(database_profile,
                                                   current_nlq_chain.get_generated_sql())
        if search_intent_result["status_code"] == 500:
            sql_search_result.data_analyse = "-1"
        else:
            if search_intent_result["data"] is not None and len(search_intent_result["data"]) > 0:
                search_intent_analyse_result = data_analyse_tool(model_type, prompt_map, search_box,
                                                                 search_intent_result["data"].to_json(
                                                                     orient='records', force_ascii=False), "query")

                sql_search_result.data_analyse = search_intent_analyse_result

                model_select_type, show_select_data = data_visualization(model_type, search_box,
                                                                         search_intent_result["data"],
                                                                         database_profile['prompt_map'])

                sql_search_result.sql_data = show_select_data
                sql_search_result.data_show_type = model_select_type
                # sql_search_result.sql_data = [list(search_intent_result["data"].columns)] + search_intent_result[
                #     "data"].values.tolist()

        answer = Answer(query=search_box, query_intent="normal_search", knowledge_search_result=knowledge_search_result,
                        sql_search_result=sql_search_result, agent_search_result=agent_search_response,
                        suggested_question=generate_suggested_question_list)
        return answer
    else:
        sub_search_task = []
        for i in range(len(agent_search_result)):
            each_task_res = get_sql_result_tool(database_profile, agent_search_result[i]["sql"])
            if each_task_res["status_code"] == 200 and len(each_task_res["data"]) > 0:
                agent_search_result[i]["data_result"] = each_task_res["data"].to_json(
                    orient='records')
                filter_deep_dive_sql_result.append(agent_search_result[i])
                each_task_sql_res = [list(each_task_res["data"].columns)] + each_task_res["data"].values.tolist()
                each_task_sql_search_result = TaskSQLSearchResult(sub_task_query=agent_search_result[i]["query"],
                                                              sql_data=each_task_sql_res,
                                                              sql=each_task_res["sql"], data_show_type="table",
                                                              sql_gen_process="",
                                                              data_analyse="")
                agent_sql_search_result.append(each_task_sql_search_result)
                sub_search_task.append(agent_search_result[i]["query"])
        agent_data_analyse_result = data_analyse_tool(model_type, prompt_map, search_box,
                                                      json.dumps(filter_deep_dive_sql_result, ensure_ascii=False),
                                                      "agent")
        logger.info("agent_data_analyse_result")
        logger.info(agent_data_analyse_result)
        agent_search_response.agent_summary = agent_data_analyse_result
        agent_search_response.agent_sql_search_result = agent_sql_search_result

        answer = Answer(query=search_box, query_intent="agent_search", knowledge_search_result=knowledge_search_result,
                        sql_search_result=sql_search_result, agent_search_result=agent_search_response,
                        suggested_question=generate_suggested_question_list)
        return answer


def user_feedback_upvote(data_profiles: str, query: str, query_intent: str, query_answer_list):
    try:
        if query_intent == "normal_search":
            if len(query_answer_list) > 0:
                VectorStore.add_sample(data_profiles, query_answer_list[0].query, query_answer_list[0].sql)
        elif query_intent == "agent_search":
            query_list = []
            for each in query_answer_list:
                query_list.append(each.query)
                VectorStore.add_sample(data_profiles, each.query, each.sql)
            VectorStore.add_agent_cot_sample(data_profiles, query, "\n".join(query_list))
        return True
    except Exception as e:
        return False


def get_nlq_chain(question: Question) -> NLQChain:
    logger.debug(question)
    verify_parameters(question)
    current_nlq_chain = __process_nlq_chain(question)
    return current_nlq_chain


def ask_with_response_stream(question: Question, current_nlq_chain: NLQChain) -> dict:
    logger.info('try to get generated sql from LLM')
    response = get_result_from_llm(question, current_nlq_chain, True)
    logger.info("got llm response")
    return response


def explain_with_response_stream(current_nlq_chain: NLQChain) -> dict:
    endpoint_name = os.getenv("SAGEMAKER_ENDPOINT_EXPLAIN")
    explain = sagemaker_to_explain(endpoint_name, current_nlq_chain.get_generated_sql(), True)
    return explain


def get_executed_result(current_nlq_chain: NLQChain) -> str:
    sql_query_result = current_nlq_chain.get_executed_result_df(all_profiles[current_nlq_chain.profile])
    final_sql_query_result = sql_query_result.to_markdown()
    return final_sql_query_result
