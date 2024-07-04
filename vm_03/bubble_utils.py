import json
import urllib.parse

def health_cards_bubble(formatted_result):
    with open('card_edit.json', encoding='utf-8') as f:
        bubble = json.load(f)
        bubble['body']['contents'][0]['contents'][0]['contents'][0]['url'] = formatted_result['image']
        bubble['body']['contents'][0]['contents'][1]['contents'][0]['contents'][1]['text'] = f"{formatted_result['p_n']}"
        bubble['body']['contents'][0]['contents'][1]['contents'][1]['contents'][1]['text'] = f"{formatted_result['p_g']}"
        bubble['body']['contents'][0]['contents'][1]['contents'][2]['contents'][1]['text'] = f"{formatted_result['p_t']}"
        bubble['body']['contents'][0]['contents'][1]['contents'][3]['contents'][1]['text'] = f"{formatted_result['p_v']}"
        bubble['body']['contents'][0]['contents'][1]['contents'][4]['contents'][1]['text'] = f"{formatted_result['p_w']}公斤"
        bubble['body']['contents'][0]['contents'][1]['contents'][5]['contents'][1]['text'] = f"{formatted_result['p_b']}({formatted_result['age']}歲)"
        bubble['body']['contents'][0]['contents'][1]['contents'][6]['contents'][1]['text'] = f"{formatted_result['p_va']}"
        bubble['body']['contents'][0]['contents'][1]['contents'][7]['contents'][1]['text'] = f"{formatted_result['n_va_re']}"
        bubble['footer']['contents'][0]['action']['data'] = json.dumps({
            'action': 'select_pet',
            'p_n': formatted_result['p_n'],
            'image': formatted_result['image'],
        #     'pet_gender': formatted_result['pet_gender'],
            'p_t': formatted_result['p_t'],
            'p_v': formatted_result['p_v'],
            'p_w': formatted_result['p_w'],
        #     'pet_birth': formatted_result['pet_birth'],
        #     'pet_vaccination': formatted_result['pet_vaccination'],
        #     'next_vaccination_reminder': formatted_result['next_vaccination_reminder'],
            'age': formatted_result['age']
        })

        bubble['footer']['contents'][1]['action']['data'] =  json.dumps({
            'action': 'delete_pet',
            'p_n': formatted_result['p_n'],
            'image': formatted_result['image'],
        #     'pet_gender': formatted_result['pet_gender'],
            'p_t': formatted_result['p_t'],
            'p_v': formatted_result['p_v'],
            'p_w': formatted_result['p_w'],
        #     'pet_birth': formatted_result['pet_birth'],
        #     'pet_vaccination': formatted_result['pet_vaccination'],
        #     'next_vaccination_reminder': formatted_result['next_vaccination_reminder'],
            'age': formatted_result['age']
        })


        # # URL encode the parameters
        params = {
            'p_n': formatted_result['p_n'],
            'p_g': formatted_result['p_g'],
            'p_t': formatted_result['p_t'],
            'p_v': formatted_result['p_v'],
            'p_w': formatted_result['p_w'],
            'p_b': formatted_result['p_b'],
            'p_va': formatted_result['p_va'],
            'n_va_re': formatted_result['n_va_re'],
            'image': formatted_result['image']
        }
        encoded_params = urllib.parse.urlencode(params)
        bubble['footer']['contents'][2]['action']['uri'] = f"https://liff.line.me/2005517118-y7Y7mPLA?{encoded_params}"
        
    return bubble

def create_carousel(formatted_results):
    carousel = {
        'type': 'carousel',
        'contents': []
    }
    for formatted_result in formatted_results:
        bubble = health_cards_bubble(formatted_result)
        carousel['contents'].append(bubble)
    return carousel
