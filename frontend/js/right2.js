// 初始化echart实例对象
var right2Chart = echarts.init(document.getElementById('right2'), 'dark');

// ----------右2的配置项 - 价格区间气泡图------------
var option = {
    title: {
        text: "景点价格区间分布",
        textStyle: {
            color: 'white',
        },
        left: 'center',
        top: '5px'
    },
    tooltip: {
        formatter: function(params) {
            return '价格区间: ' + params.data.name + '<br/>景点数量: ' + (params.data.value[1] || params.data.value);
        }
    },
    grid: {
        left: '8%',
        right: '10%',
        bottom: '15%',
        top: '60px',
        containLabel: true
    },
    xAxis: {
        type: 'value',
        name: '价格(元)',
        nameLocation: 'middle',
        nameGap: 25,
        nameTextStyle: {
            color: 'rgba(255,255,255,0.7)',
            fontSize: 12
        },
        min: 0,
        max: 500,
        axisLine: {
            show: true,
            lineStyle: {
                color: 'rgba(255,255,255,0.3)'
            }
        },
        axisTick: {
            show: false
        },
        axisLabel: {
            color: 'rgba(255,255,255,0.7)',
            fontSize: 10,
            formatter: function(value) {
                return value;
            }
        },
        splitLine: {
            lineStyle: {
                color: 'rgba(255,255,255,0.1)'
            }
        }
    },
    yAxis: {
        type: 'value',
        name: '景点数量',
        nameLocation: 'middle',
        nameGap: 35,
        nameTextStyle: {
            color: 'rgba(255,255,255,0.7)',
            fontSize: 12
        },
        axisLine: {
            show: true,
            lineStyle: {
                color: 'rgba(255,255,255,0.3)'
            }
        },
        axisTick: {
            show: false
        },
        axisLabel: {
            color: 'rgba(255,255,255,0.7)',
            fontSize: 10
        },
        splitLine: {
            lineStyle: {
                color: 'rgba(255,255,255,0.1)'
            }
        }
    },
    series: [{
        type: 'scatter',
        data: [],
        symbolSize: function(data) {
            // 气泡大小根据数量缩放，最大50
            var size = data[2] || data.value;
            var base = Math.sqrt(size) * 2.3;
            return Math.max(8, Math.min(90, base));
        },
        itemStyle: {
            color: new echarts.graphic.RadialGradient(0.4, 0.3, 1, [
                { offset: 0, color: 'rgb(129, 227, 238)' },
                { offset: 1, color: 'rgb(25, 183, 207)' }
            ])
        },
        emphasis: {
            label: {
                show: true,
                formatter: function(param) {
                    var count = param.data.value[1] || param.data.value;
                    return param.data.name + '\n数量: ' + count;
                },
                position: 'top',
                color: '#00E5FF',
                fontSize: 12
            }
        }
    }]
};

// 使用刚指定的配置项和数据显示图表
right2Chart.setOption(option);

// 从后端获取价格区间分布数据
function fetchPriceDistribution() {
    fetch('http://localhost:8000/api/price_distribution')
        .then(response => response.json())
        .then(result => {
            if (result.success && result.data.length > 0) {
                // 转换数据格式：scatter需要 [x, y, size] 或 {value: [x, y], symbolSize: n}
                var chartData = result.data.map(function(item) {
                    return {
                        name: item.name,
                        value: [item.xAxis, item.value, item.value]  // [x, y, bubbleSize]
                    };
                });

                right2Chart.setOption({
                    series: [{
                        data: chartData
                    }]
                });
            }
        })
        .catch(function(err) {
            console.error('获取价格分布数据失败:', err);
        });
}

// 首次加载
fetchPriceDistribution();

// 每 10 秒刷新一次数据
setInterval(fetchPriceDistribution, 10000);
