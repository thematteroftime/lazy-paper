// lazy-paper garden — Tweaks bridge (React island → vanilla canvas app)
const GARDEN_TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "skin": "dark",
  "paperCount": 60,
  "clusterCount": 5,
  "coolingDays": 7,
  "spikeForm": "cross",
  "linkBudget": 50,
  "nebula": 60,
  "zoomDur": 0.9,
  "drift": 1
}/*EDITMODE-END*/;

function GardenTweaks() {
  const [t, setTweak] = useTweaks(GARDEN_TWEAK_DEFAULTS);
  React.useEffect(() => {
    if (window.GardenApp) window.GardenApp.applyTweaks(t);
  }, [t]);
  return (
    <TweaksPanel title="Tweaks">
      <TweakSection label="皮肤" />
      <TweakRadio label="基调(§7.1)" value={t.skin}
        options={[{value:'dark',label:'暗空'},{value:'paper',label:'纸上星图'},{value:'myc',label:'菌丝'}]}
        onChange={(v) => setTweak('skin', v)} />
      <TweakSection label="数据" />
      <TweakSlider label="库规模(论文数)" value={t.paperCount} min={1} max={220} step={1}
        onChange={(v) => setTweak('paperCount', v)} />
      <TweakSlider label="聚类数" value={t.clusterCount} min={3} max={6} step={1}
        onChange={(v) => setTweak('clusterCount', v)} />
      <TweakButton label="✶ 模拟 ingest 一篇" onClick={() => window.GardenApp && window.GardenApp.ingest()} />
      <TweakSection label="视觉" />
      <TweakRadio label="星芒形态(§7.2)" value={t.spikeForm}
        options={[{value:'cross',label:'十字'},{value:'six',label:'六芒'},{value:'etch',label:'刻线'}]}
        onChange={(v) => setTweak('spikeForm', v)} />
      <TweakSlider label="冷却周期(§7.3)" value={t.coolingDays} min={2} max={30} step={1} unit=" 天"
        onChange={(v) => setTweak('coolingDays', v)} />
      <TweakSlider label="连线预算(§6.3)" value={t.linkBudget} min={0} max={80} step={5}
        onChange={(v) => setTweak('linkBudget', v)} />
      <TweakSlider label="星云浓度" value={t.nebula} min={0} max={100} step={5}
        onChange={(v) => setTweak('nebula', v)} />
      <TweakSlider label="流动性(星体漂移)" value={t.drift} min={0} max={2} step={0.1}
        onChange={(v) => setTweak('drift', v)} />
      <TweakSection label="镜头" />
      <TweakSlider label="变焦时长" value={t.zoomDur} min={0.4} max={1.6} step={0.1} unit=" s"
        onChange={(v) => setTweak('zoomDur', v)} />
    </TweaksPanel>
  );
}

ReactDOM.createRoot(document.getElementById('tweaks-root')).render(<GardenTweaks />);
