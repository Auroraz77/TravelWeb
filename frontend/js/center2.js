// 初始化echart实例对象
var myChart = echarts.init(document.getElementById('center2'), 'dark');

// ----------假期出行数据地图配置------------
var option = {
    title: {
        text: '假期出行数据地图分布',
        textStyle: {
            color: 'gold',
            fontStyle: 'normal',
        },
        left: 'center',
        top: '20px'
    },
    tooltip: {
        trigger: 'item',
        formatter: function(params) {
            return params.name + '<br/>销量: ' + (params.value || 0);
        }
    },
    visualMap: {
        show: true,
        x: 'left',
        y: 'bottom',
        textStyle: {
            fontSize: 10,
            color: '#fff'
        },
        splitList: [
            { start: 0, end: 10000 },
            { start: 10000, end: 50000 },
            { start: 50000, end: 100000 },
            { start: 100000, end: 500000 },
            { start: 500000 }
        ],
        color: ['#1a5276', '#2874a6', '#3498db', '#5dade2', '#aed6f1']
    },
    series: [{
        name: '景点销量',
        type: 'map',
        mapType: 'china',
        roam: false,
        itemStyle: {
            normal: {
                borderWidth: 0.5,
                borderColor: '#009fe8',
                areaColor: "#1a1a2e",
            },
            emphasis: {
                borderWidth: 0.5,
                borderColor: '#4b0082',
                areaColor: "#16213e",
            }
        },
        label: {
            normal: {
                show: true,
                fontSize: 8,
                color: 'black'
            },
            emphasis: {
                show: true,
                fontSize: 10,
            }
        },
        data: []
    }]
};

// 使用刚指定的配置项和数据显示图表
myChart.setOption(option);

// 从后端获取各省销量汇总数据
function fetchSalesByProvince() {
    fetch('http://localhost:8000/api/sales_by_province')
        .then(response => response.json())
        .then(result => {
            if (result.success) {
                myChart.setOption({
                    series: [{
                        data: result.data
                    }]
                });
            }
        })
        .catch(function(err) {
            console.error('获取省份销量数据失败:', err);
        });
}

// 首次加载
fetchSalesByProvince();

// 每 5 秒刷新一次地图数据
setInterval(fetchSalesByProvince, 5000);
