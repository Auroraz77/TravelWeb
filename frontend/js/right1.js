// 初始化echart实例对象
var right1Chart = echarts.init(document.getElementById('right1'), 'dark');

// ----------右1的配置项-------------------
var option = {
    title: {
        text: "今日销量 TOP10 景点",
        textStyle: {
            color: 'white',
        },
        left: 'center'
    },
    color: ['#3398DB'],
    tooltip: {
        trigger: 'axis',
        axisPointer: {
            type: 'shadow'
        }
    },
    grid: {
        left: '3%',
        right: '8%',
        bottom: '3%',
        top: 50,
        containLabel: true
    },
    xAxis: {
        type: 'value',
        axisLabel: {
            show: true,
            color: 'white',
            fontSize: 12,
            formatter: function(value) {
                if (value >= 1000) {
                    value = value / 1000 + 'k';
                }
                return value;
            }
        },
        axisLine: {
            show: true,
            lineStyle: {
                color: 'rgba(255,255,255,0.3)'
            }
        },
        splitLine: {
            lineStyle: {
                color: 'rgba(255,255,255,0.1)'
            }
        }
    },
    yAxis: {
        type: 'category',
        data: [],
        axisLabel: {
            color: 'white',
            fontSize: 11
        },
        axisLine: {
            show: false
        },
        axisTick: {
            show: false
        }
    },
    series: [{
        data: [],
        type: 'bar',
        barWidth: '50%',
        label: {
            show: true,
            position: 'right',
            color: '#00E5FF',
            fontSize: 11,
            fontWeight: 'bold'
        },
        itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                { offset: 0, color: 'rgba(0, 80, 160, 0.6)' },
                { offset: 1, color: '#00E5FF' }
            ]),
            borderRadius: [0, 5, 5, 0]
        }
    }]
};

right1Chart.setOption(option);

// 每 2 秒从后端获取实时排名数据
function fetchLiveRanking() {
    fetch('http://localhost:8000/api/live_ranking')
        .then(response => response.json())
        .then(result => {
            if (result.success) {
                var names = [];
                var values = [];

                // 注意：横向柱状图 Y 轴默认从下往上，需要 reverse() 让第一名在上
                result.data.reverse().forEach(function(item) {
                    names.push(item['名称']);
                    values.push(item.today_sales);
                });

                right1Chart.setOption({
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
            console.error('获取排名数据失败:', err);
        });
}

fetchLiveRanking();
setInterval(fetchLiveRanking, 500);
