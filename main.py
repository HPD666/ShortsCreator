<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shorts Trend & Öncü Influencer Bulucu</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 20px; background-color: #0f0f0f; color: #f1f1f1; }
        .container { max-width: 900px; margin: auto; background: #212121; padding: 30px; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.5); }
        h2 { color: #ff0000; margin-top: 0; }
        input { padding: 14px; margin: 10px 0; width: 100%; box-sizing: border-box; border-radius: 8px; border: 1px solid #3d3d3d; background: #121212; color: #fff; font-size: 15px; }
        button { padding: 14px; width: 100%; background-color: #ff0000; color: white; border: none; font-weight: bold; border-radius: 8px; font-size: 16px; cursor: pointer; transition: 0.2s; }
        button:hover { background-color: #cc0000; }
        .card { background: #181818; border: 1px solid #333; padding: 20px; margin-top: 20px; border-radius: 8px; border-left: 6px solid #ff0000; }
        .card-header { font-size: 18px; font-weight: bold; color: #fff; margin-bottom: 8px; }
        .badge { background: #2a2a2a; color: #aaa; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; margin-right: 8px; display: inline-block; }
        .badge-pioneer { background: #1b5e20; color: #a5d6a7; border: 1px solid #2e7d32; }
        .error-box { background: #b71c1c; color: #fff; padding: 15px; border-radius: 8px; margin-top: 15px; }
        a { color: #3ea6ff; text-decoration: none; font-weight: 600; }
        a:hover { text-decoration: underline; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin: 12px 0; background: #282828; padding: 12px; border-radius: 6px; }
    </style>
</head>
<body>

<div class="container">
    <h2>🎯 Kesin Trend & Öncü Influencer Tespiti</h2>
    <p style="color: #aaa; font-size: 14px;">API Key'inizi girip butona basın. Sistem otomatik olarak Shorts akımlarını tarayıp ilk yükleyen kanalı tespit edecektir.</p>
    
    <input type="text" id="apiKey" placeholder="YouTube Data API Key Giriniz">
    <button onclick="runPioneerDetection()">Otomatik Trend Analizini Çalıştır</button>

    <div id="results"></div>
</div>

<script>
function tokenize(text) {
    return text.toLowerCase()
        .replace(/[^a-z0-9ğüşıöç# ]/gi, '')
        .split(/\s+/)
        .filter(w => w.length > 2);
}

function getSimilarity(text1, text2) {
    const tokens1 = tokenize(text1);
    const tokens2 = tokenize(text2);
    if (!tokens1.length || !tokens2.length) return 0;

    const set1 = new Set(tokens1);
    const set2 = new Set(tokens2);

    let intersection = 0;
    set1.forEach(t => { if (set2.has(t)) intersection++; });

    return intersection / (set1.size + set2.size - intersection);
}

async function runPioneerDetection() {
    const apiKey = document.getElementById('apiKey').value.trim();
    const resultsDiv = document.getElementById('results');

    if (!apiKey) {
        alert("Lütfen geçerli bir API Key girin!");
        return;
    }

    resultsDiv.innerHTML = "<p style='color:#aaa;'>1/4: Shorts verileri çekiliyor...</p>";

    try {
        // Geniş arama parametresi ile güncel Shorts içeriklerini çekme
        const searchUrl = `https://www.googleapis.com/youtube/v3/search?part=snippet&maxResults=50&q=shorts&type=video&videoDuration=short&key=${apiKey}`;
        const searchRes = await fetch(searchUrl);
        const searchData = await searchRes.json();

        if (searchData.error) {
            resultsDiv.innerHTML = `
                <div class="error-box">
                    <strong>API Hatası Oluştu!</strong><br>
                    Kod: ${searchData.error.code}<br>
                    Mesaj: ${searchData.error.message}
                </div>`;
            return;
        }

        if (!searchData.items || searchData.items.length === 0) {
            resultsDiv.innerHTML = "<p>Video verisi dönmedi. Lütfen tekrar deneyin.</p>";
            return;
        }

        const videoIds = searchData.items.map(i => i.id.videoId).join(',');
        const channelIds = [...new Set(searchData.items.map(i => i.snippet.channelId))].join(',');

        resultsDiv.innerHTML = "<p style='color:#aaa;'>2/4: Yayınlanma zamanları ve kanal bilgileri çekiliyor...</p>";

        const videoStatsUrl = `https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&id=${videoIds}&key=${apiKey}`;
        const channelStatsUrl = `https://www.googleapis.com/youtube/v3/channels?part=statistics&id=${channelIds}&key=${apiKey}`;

        const [videoRes, channelRes] = await Promise.all([
            fetch(videoStatsUrl).then(r => r.json()),
            fetch(channelStatsUrl).then(r => r.json())
        ]);

        const channelMap = {};
        if (channelRes.items) {
            channelRes.items.forEach(c => {
                channelMap[c.id] = parseInt(c.statistics.subscriberCount || 0);
            });
        }

        const processedVideos = videoRes.items.map(item => {
            return {
                id: item.id,
                title: item.snippet.title,
                description: item.snippet.description,
                fullText: `${item.snippet.title} ${item.snippet.description}`,
                views: parseInt(item.statistics.viewCount || 0),
                channelTitle: item.snippet.channelTitle,
                subscribers: channelMap[item.snippet.channelId] || 0,
                publishedAt: new Date(item.snippet.publishedAt).getTime(),
                publishedAtFormatted: new Date(item.snippet.publishedAt).toLocaleString('tr-TR'),
                url: `https://www.youtube.com/shorts/${item.id}`
            };
        });

        resultsDiv.innerHTML = "<p style='color:#aaa;'>3/4: Zaman analizi ve taklit eşleştirmesi yapılıyor...</p>";

        const clusters = [];
        const similarityThreshold = 0.20; // Esnek benzerlik oranı

        processedVideos.forEach(video => {
            let matchedCluster = null;

            for (let cluster of clusters) {
                const sim = getSimilarity(video.fullText, cluster.referenceText);
                if (sim >= similarityThreshold) {
                    matchedCluster = cluster;
                    break;
                }
            }

            if (matchedCluster) {
                matchedCluster.videos.push(video);
                matchedCluster.totalViews += video.views;

                // Tarihi daha eski olan videoyu ilk yükleyen (öncü) yap
                if (video.publishedAt < matchedCluster.pioneerVideo.publishedAt) {
                    matchedCluster.pioneerVideo = video;
                }
            } else {
                clusters.push({
                    referenceText: video.fullText,
                    pioneerVideo: video,
                    videos: [video],
                    totalViews: video.views
                });
            }
        });

        const activeTrends = clusters
            .filter(c => c.videos.length > 1)
            .sort((a, b) => b.videos.length - a.videos.length)
            .slice(0, 5);

        resultsDiv.innerHTML = "<h3>🔥 Tespit Edilen Akımlar ve İlk Yükleyen Öncüler</h3>";

        if (activeTrends.length === 0) {
            resultsDiv.innerHTML += "<p>Ayrıştırılabilir bir taklit kümesi bulunamadı. Butona tekrar basarak yeni verileri taratabilirsiniz.</p>";
            return;
        }

        activeTrends.forEach((trend, idx) => {
            const pioneer = trend.pioneerVideo;
            const isInfluencer = pioneer.subscribers >= 100000;

            resultsDiv.innerHTML += `
                <div class="card">
                    <div class="card-header">#${idx + 1} Akım: "${pioneer.title}"</div>
                    <div>
                        <span class="badge badge-pioneer">👑 Akımı İlk Başlatan: ${pioneer.channelTitle} (${pioneer.subscribers.toLocaleString('tr-TR')} Abone)</span>
                        <span class="badge">Taklit Edilme Sayısı: ${trend.videos.length - 1} Video</span>
                        ${isInfluencer ? '<span class="badge" style="background:#4a148c; color:#e1bee7;">Onaylı Influencer</span>' : ''}
                    </div>
                    <div class="stats-grid">
                        <div><strong>İlk Yüklenme Tarihi:</strong> ${pioneer.publishedAtFormatted}</div>
                        <div><strong>Öncü Video İzlenmesi:</strong> ${pioneer.views.toLocaleString('tr-TR')}</div>
                        <div><strong>Akımın Toplam İzlenmesi:</strong> ${trend.totalViews.toLocaleString('tr-TR')}</div>
                    </div>
                    <p><a href="${pioneer.url}" target="_blank">Akımın Çıktığı İlk Short'u İzle ➔</a></p>
                </div>
            `;
        });

    } catch (err) {
        console.error(err);
        resultsDiv.innerHTML = "<div class='error-box'>İstek işlenirken bağlantı veya veri hatası oluştu. Konsolu inceleyebilirsiniz.</div>";
    }
}
</script>

</body>
</html>
