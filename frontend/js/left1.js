// 初始化echart实例对象
var left1Chart = echarts.init(document.getElementById('left1'), 'dark');

// ----------左1的配置项 - 热门景点销量TOP20---------------
var option = {
    title: {
        text: "热门景点销量数据",
        textStyle: {
            color: 'white',
        },
        left: 'left',
    },
    tooltip: {
        trigger: 'axis',
        axisPointer: {
            type: 'shadow'
        }
    },
    grid: {
        left: '3%',
        right: '20%',
        bottom: '3%',
        top: 60,
        containLabel: true
    },
    xAxis: {
        type: 'value',
        axisLine: {
            show: false
        },
        axisTick: {
            show: false
        },
        axisLabel: {
            show: false
        },
        splitLine: {
            show: false
        }
    },
    yAxis: {
        type: 'category',
        data: [],
        axisLine: {
            show: false
        },
        axisTick: {
            show: false
        },
        axisLabel: {
            color: 'rgba(200, 220, 255, 0.8)',
            fontSize: 11
        }
    },
    series: [{
        name: "销量",
        type: 'bar',
        barWidth: 15,
        data: [],
        itemStyle: {
            borderRadius: [0, 6, 6, 0],
            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                { offset: 0, color: '#0039CB' },
                { offset: 0.7, color: '#9B59B6' },
                { offset: 1, color: '#E74C3C' }
            ])
        },
        label: {
            show: true,
            position: 'right',
            color: '#00E5FF',
            fontSize: 11,
            fontWeight: 'bold',
            formatter: '{c}'
        }
    }]
};

left1Chart.setOption(option);

// 从后端获取历史销量 TOP20 数据
function fetchTopHistorySales() {
    fetch('http://localhost:8000/api/top_history_sales')
        .then(response => response.json())
        .then(result => {
            if (result.success && result.data.length > 0) {
                var names = [];
                var values = [];

                result.data.reverse().forEach(function(item) {
                    names.push(item['名称']);
                    values.push(item['销量']);
                });

                left1Chart.setOption({
                    yAxis: {
                        data: names
                    },
                    series: [{
                        data: values
                    }]
                });
            }
        })
        .catch(function(err) {
            console.error('获取历史销量数据失败:', err);
        });
}

fetchTopHistorySales();
