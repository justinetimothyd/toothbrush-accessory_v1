from flask import Flask, request, jsonify
import base64
import re
import json
import google.generativeai as genai

genai.configure(api_key="AIzaSyDZK54jFzMY5Z46WOcfWO-bzAIUH_Ou3Yg")  

app = Flask(__name__)

@app.route('/analyze-image', methods=['POST'])
def analyze_image():
    try:
        if 'image' not in request.files:
            return jsonify({"error": "No image file provided"}), 400

        image_file = request.files['image']
        image_data = image_file.read()

     
        model = genai.GenerativeModel("gemini-2.0-flash-lite")
        response = model.generate_content([
            {"mime_type": "image/jpeg", "data": image_data},
            """
            Analyze this image of teeth for dental health assessment.

            For each area of interest, identify:
            1. Areas that appear to have caries (cavities/decay)
            2. Areas with visible plaque buildup
            3. Areas that appear healthy

            Return a structured JSON response with:
            1. Predictions with bounding boxes [y0, x0, y1, x1] for each detection
            2. Practical recommendations for dental care
            3. Keep classes simple: "caries", "plaque", "healthy"

            JSON format:
            {
              "predictions": [
                {
                  "class": "caries",
                  "confidence": 0.92,
                  "box_2d": [y0, x0, y1, x1]
                }
              ],
              "recommendations": [
                "Consider brushing twice daily",
                "Use fluoride toothpaste",
                "Schedule a dental checkup"
              ]
            }
            """
        ])

        print("\u2699\ufe0f  Raw Gemini Response:")
        print(repr(response.text))  

        # test(debug) 
        if not response.text.strip():
            return jsonify({
                "error": "Gemini returned an empty response. Possibly filtered for safety."
            }), 502

        #
        match = re.search(r'```json\s*(\{.*?\})\s*```', response.text, re.DOTALL)
        raw_json = match.group(1) if match else response.text

        try:
            
            clean_json = re.sub(r"(?<!\\)'", '"', raw_json)  
            parsed = json.loads(clean_json)
            
            if "predictions" not in parsed:
                parsed["predictions"] = []
                
            if "recommendations" not in parsed:
                parsed["recommendations"] = [
                    "Brush your teeth twice daily",
                    "Use fluoride toothpaste",
                    "Floss once a day",
                    "Visit your dentist regularly"
                ]
            
            for pred in parsed["predictions"]:
                if "class" in pred:
                    pred["class"] = pred["class"].replace("-like", "").replace("-looking", "")
                
                if "confidence" in pred and isinstance(pred["confidence"], (int, float)):
                    pred["confidence"] = max(0.0, min(1.0, float(pred["confidence"])))
                else:
                    pred["confidence"] = 0.85  
                    
                if "box_2d" not in pred or not isinstance(pred["box_2d"], list) or len(pred["box_2d"]) != 4:
                    pred["box_2d"] = [100, 100, 200, 200]
            
            return jsonify({"response": parsed})
        except Exception as parse_err:
            return jsonify({
                "error": "Failed to parse Gemini response",
                "raw": response.text,
                "parse_error": str(parse_err)
            }), 500

    except Exception as e:
        return jsonify({"error": f"Exception: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080)