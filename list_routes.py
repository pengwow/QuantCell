import requests
from bs4 import BeautifulSoup

# 从API文档中提取所有路由
def list_routes():
    url = "http://localhost:8000/docs"
    
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 查找所有路由
        routes = []
        for tag in soup.find_all("span", class_="opblock-summary-method"):
            method = tag.text.strip()
            path = tag.find_next_sibling("span", class_="opblock-summary-path").text.strip()
            routes.append((method, path))
        
        # 排序并打印路由
        routes.sort()
        print("所有已注册的路由:")
        print("=" * 60)
        for method, path in routes:
            print(f"{method.ljust(10)} {path}")
        
        return routes
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    list_routes()