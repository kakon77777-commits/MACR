# MACR v0.6 Live Gate Runbook（未執行）

狀態：**只是一份 operator-controlled runbook；本文件不授權 provider 呼叫、共享狀態遷移、部署或自動化。**

## 固定前提

- 被測主體必須是獨立重播通過的精確 commit/tree，且工作樹乾淨。
- v0.4 invoker census 必須為 0；任何舊 writer 再出現都立即停止。
- 既有 legacy JSONL 必須仍是唯讀、41,490 bytes、74 筆有效且互異事件、SHA-256 `80AF74FB9FB20FF805E168F13A40E4DC585DA20AEA3778347FDDE6CC29128299`。
- runtime DB 必須已有該 74-event source 的 complete row，重播 reconciliation 必須是 0 new／74 already；任何 byte、count、attribute 或 complete-row drift 都停止，不得沿用舊核准。
- 每個付費或本機生成步驟都需要該次精確 task／plan／member authority。持有 API key、queue lease 或本文件都不是 authority。
- 不得自動重試、不得靜默更換模型／route、不得把 timeout 或未知結果記成零成本。

## 順序

1. Operator 明示選定整合候選；記錄 commit、tree、schema versions、provider census 與乾淨狀態。
2. 獨立 verifier 在離線環境連跑 `scripts\verify-v06.ps1` 兩次；兩份 `V06_SUMMARY` 必須 byte-identical。
3. 重新檢查 legacy seal、74-event reconciliation、active queue/dispatch/target leases、unsettled accounting 與 provider census。任一非零或不一致即停止。
4. 只在另行授權後，擷取一份有界、公開、內容不進 runtime/accounting 的 Observatory snapshot；discovery 只形成 observation，不形成 execution provider。
5. 只在另行授權後，執行一個公開、低成本、精確 authority 的 T0 canary。核對 dispatch／terminal、Candidate capture、return contract、verification 與 accounting；acceptance 保持 pending，直到 operator 決定。
6. 只在 T0 對帳完整後，另行授權一個序列化的 T1 three-member（三成員）batch。核對三個 exact member digest、三個不同 claim、每成員最多一次 provider attempt、aggregate ceiling、零 duplicate、零遺失、零 corrupt evidence。
7. 任一 lease expiry、transport 結果未知、terminal persistence failure 或帳務缺口都轉入 reconciliation；不得自動重試。
8. 只在前三成員完整對帳後，對至少三條 qualified candidate route 執行同一 canonical probe pack。`probe-replay` 必須重新載入實際 pack 並核對完整 case/task/context/verifier/cost 矩陣；只帶 manifest＋results 不得完成 replay。差分比較介面只顯示 blinded candidate ID；模型標籤不得進入評分列。
9. 分別記錄 discovery、probe、production execution、verification、integration 成本與 future bill observation；帳單同步仍是預留 port，不在 v0.6 自動匯入。
10. Operator 最後只能做明示 acceptance 或 route closure。綠色 provider 回應、測試、replay 或 reviewer 意見都不自行構成 merge、release、deploy、adoption 或 resident authority。

## 停止條件

遇到下列任一情況立即停止：source drift、非零舊 invoker、authority 過期或不匹配、同 target 非具名競爭、兩個 automatic materializer、aggregate hard ceiling 超額、candidate bytes 未捕獲、event/accounting 不成對、驗證圖不匹配、任何自動 fallback／retry、或任何 prompt／answer／credential／raw path 進入公共資料庫。
