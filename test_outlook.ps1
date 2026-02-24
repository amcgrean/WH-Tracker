$outlook = New-Object -ComObject Outlook.Application
$namespace = $outlook.GetNameSpace("MAPI")
$inbox = $namespace.GetDefaultFolder(6) # 6 = Inbox
$items = $inbox.Items
$items | Sort-Object ReceivedTime -Descending | Select-Object -First 5 Subject, ReceivedTime, SenderName | Format-Table -AutoSize
