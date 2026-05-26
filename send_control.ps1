param(
    [Parameter(Mandatory=$false)]
    [ValidateSet('sim','gui')]
    [string]$Target = 'gui',

    [Parameter(Mandatory=$false)]
    [ValidateSet('ping','status','stop','help')]
    [string]$Command = 'status',

    [Parameter(Mandatory=$false)]
    [int]$Port
)

if (-not $Port) {
    if ($Target -eq 'sim') {
        $Port = 9031
    } else {
        $Port = 9032
    }
}

$client = New-Object System.Net.Sockets.TcpClient
try {
    $client.Connect('127.0.0.1', $Port)
    $stream = $client.GetStream()

    $writer = New-Object System.IO.StreamWriter($stream)
    $writer.NewLine = "`n"
    $writer.AutoFlush = $true
    $writer.WriteLine($Command)

    $reader = New-Object System.IO.StreamReader($stream)
    $response = $reader.ReadLine()
    if ($null -eq $response) {
        Write-Output 'No response'
    } else {
        Write-Output $response
    }
}
catch {
    Write-Error "Failed to send '$Command' to 127.0.0.1:$Port - $($_.Exception.Message)"
    exit 1
}
finally {
    if ($client) {
        $client.Dispose()
    }
}
