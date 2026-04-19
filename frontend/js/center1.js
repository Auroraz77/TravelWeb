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
    // 先预取一个新景点
    fetchRandomAttraction();

    // 等有景点再切换
    if (attractions.length > 0) {
        // 每次切换都取最新的一个
        currentAttractionIndex = attractions.length - 1;
        updateDisplay(attractions[currentAttractionIndex]);
    }
}

// 初始加载5个景点
for (var i = 0; i < 5; i++) {
    fetchRandomAttraction();
}

// 每3秒切换景点，同时预取新的
setInterval(switchAttraction, 3000);
