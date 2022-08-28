from google.cloud import storage


#sto_url = "https://storage.cloud.google.com/mdx-hsr/"

sto_client = storage.Client.from_service_account_json('mdx-stt.json')
sto_bucket = sto_client.bucket('mdx-hsr')

blob = sto_bucket.blob("test-in-storage")
blob.upload_from_filename("test.txt")

#blob.make_public()

