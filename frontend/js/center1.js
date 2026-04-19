// 景点简介展示面板
// 每3秒切换一个景点的名称和简介

var currentAttractionIndex = 0;
var attractions = [];

function fetchRandomAttraction() {
    fetch('http://localhost:8000/api/random_attraction')
        .then(response => response.json())
        .then(result => {
            if (result.success) {
                attractions.push(result.data);
                if (attractions.length > 10) {
                    attractions.shift();
                }
                if (attractions.length === 1) {
                    updateDisplay(result.data);
                }
            } else {
                console.error('获取景点失败:', result.error);
            }
        })
        .catch(err => {
            console.error('请求接口失败:', err);
        });
}

function updateDisplay(attraction) {
    // 更新景点名称
    document.getElementById('confirm').innerText = attraction.name;
    // 更新城市标签
    document.getElementById('heal').innerText = attraction.city;
    // 更新描述
    document.getElementById('dead').innerText = attraction.description;
}

function switchAttraction() {
    if (attractions.length > 0) {
        currentAttractionIndex = (currentAttractionIndex + 1) % attractions.length;
        updateDisplay(attractions[currentAttractionIndex]);
    }
}

// 先预加载一些景点数据
for (var i = 0; i < 3; i++) {
    fetchRandomAttraction();
}

// 每3秒切换景点
setInterval(switchAttraction, 3000);
