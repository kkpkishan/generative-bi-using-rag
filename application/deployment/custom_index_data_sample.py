
bulk_questions = [
    # 1. The following is an example of Sample QA pair
    {"question": "Which hospital has the highest annual revenue?",
     "sql": '''
     select name, revenue from table_a
     order by
     CASE
        WHEN revenue = '500~1000W' THEN 1
        WHEN revenue = '1000~3000W' THEN 2
     END
     desc
     limit 10
    '''}
]

for q in bulk_questions:
    # 2. Please modify profile_name to be consistent with Data Profile name
    q['profile'] = '<profile_name>'

custom_bulk_questions = {
    'custom': bulk_questions
}