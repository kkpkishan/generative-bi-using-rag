import logging

from nlq.business.connection import ConnectionManagement
from utils.domain import SearchTextSqlResult
from utils.llm import text_to_sql
from utils.opensearch import get_retrieve_opensearch
from utils.tool import get_generated_sql

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def normal_text_search(search_box, model_type, database_profile, entity_slot, env_vars, selected_profile, use_rag,
                       model_provider=None):
    entity_slot_retrieve = []
    retrieve_result = []
    response = ""
    sql = ""
    search_result = SearchTextSqlResult(search_query=search_box, entity_slot_retrieve=entity_slot_retrieve,
                                        retrieve_result=retrieve_result, response=response, sql=sql)
    try:
        if database_profile['db_url'] == '':
            conn_name = database_profile['conn_name']
            db_url = ConnectionManagement.get_db_url_by_name(conn_name)
            database_profile['db_url'] = db_url
            database_profile['db_type'] = ConnectionManagement.get_db_type_by_name(conn_name)

        if len(entity_slot) > 0 and use_rag:
            for each_entity in entity_slot:
                entity_retrieve = get_retrieve_opensearch(env_vars, each_entity, "ner",
                                                          selected_profile, 1, 0.7)
                if len(entity_retrieve) > 0:
                    entity_slot_retrieve.extend(entity_retrieve)

        if use_rag:
            retrieve_result = get_retrieve_opensearch(env_vars, search_box, "query",
                                                      selected_profile, 3, 0.5)

        response = text_to_sql(database_profile['tables_info'],
                               database_profile['hints'],
                               database_profile['prompt_map'],
                               search_box,
                               model_id=model_type,
                               sql_examples=retrieve_result,
                               ner_example=entity_slot_retrieve,
                               dialect=database_profile['db_type'],
                               model_provider=model_provider)
        sql = get_generated_sql(response)
        search_result = SearchTextSqlResult(search_query=search_box, entity_slot_retrieve=entity_slot_retrieve,
                                            retrieve_result=retrieve_result, response=response, sql="")
        search_result.entity_slot_retrieve = entity_slot_retrieve
        search_result.retrieve_result = retrieve_result
        search_result.response = response
        search_result.sql = sql
    except Exception as e:
        logger.error(e)
    return search_result


def agent_text_search(search_box, model_type, database_profile, entity_slot, env_vars, selected_profile, use_rag,
                      agent_cot_task_result):
    agent_search_results = []
    try:
        for each_task in agent_cot_task_result:
            each_res_dict = {}
            each_task_query = agent_cot_task_result[each_task]
            each_res_dict["query"] = each_task_query
            entity_slot_retrieve = []
            retrieve_result = []
            if use_rag:
                entity_slot_retrieve = get_retrieve_opensearch(env_vars, each_task_query, "ner",
                                                               selected_profile, 3, 0.5)

                retrieve_result = get_retrieve_opensearch(env_vars, each_task_query, "query",
                                                          selected_profile, 3, 0.5)
            each_task_response = text_to_sql(database_profile['tables_info'],
                                             database_profile['hints'],
                                             database_profile['prompt_map'],
                                             each_task_query,
                                             model_id=model_type,
                                             sql_examples=retrieve_result,
                                             ner_example=entity_slot_retrieve,
                                             dialect=database_profile['db_type'],
                                             model_provider=None)
            each_task_sql = get_generated_sql(each_task_response)
            each_res_dict["response"] = each_task_response
            each_res_dict["sql"] = each_task_sql
            if each_res_dict["sql"] != "":
                agent_search_results.append(each_res_dict)
    except Exception as e:
        logger.error(e)
    return agent_search_results
