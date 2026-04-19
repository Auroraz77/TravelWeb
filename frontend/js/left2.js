// 初始化echart实例对象
var left2Chart = echarts.init(document.getElementById('left2'), 'dark');

// ----------左2配置项 - 各省市4A-5A景区数量玫瑰图------------
var option = {
    title: {
        text: '各省市4A-5A景区数量玫瑰图',
        textStyle: {
            color: 'white',
        },
        left: 'center',
        top: 10
    },
    tooltip: {
        trigger: 'item',
        formatter: '{b}: {c}个'
    },
    series: [
        {
            name: '4A-5A景区数量',
            type: 'pie',
            radius: [15, 160],
            center: ['45%', '65%'],
            roseType: 'area',
            itemStyle: {
                borderRadius: 5
            },
            label: {
                show: true,
                color: '#fff',
                fontSize: 8,
                position: 'inside',
                formatter: '{b}'
            },
            labelLine: {
                show: false
            },
            data: []
        }
    ]
};

left2Chart.setOption(option);

// 从后端获取各省4A/5A景区数量数据
function fetchProvince4A5ACount() {
    fetch('http://localhost:8000/api/province_4a5a_count')
        .then(response => response.json())
        .then(result => {
            if (result.success && result.data.length > 0) {
                // 按数量从大到小排序
                var sortedData = result.data.sort(function(a, b) {
                    return b.value - a.value;
                });
                left2Chart.setOption({
                    series: [{
                        data: sortedData
                    }]
                });
            }
        })
        .catch(function(err) {
            console.error('获取4A/5A景区数据失败:', err);
        });
}

// 首次加载
fetchProvince4A5ACount();
