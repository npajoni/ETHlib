import boto3

class AwsS3Exception(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)


class AwsS3(object):
    def __init__(self, access_key, secret_key):
        self.s3 = boto3.resource('s3',aws_access_key_id=access_key, aws_secret_access_key=secret_key)

    def upload(self, src_path, filename, bucket, dst_path):
        # Lease Bucket como destination path 
        if not src_path.endswith('/'):
            src_path = src_path + '/'

        try:
            with open(src_path +  filename) as f:
                buffer = f.read()

            f.close()
        except Exception as e:
            raise AwsS3Exception(str(e))

        try:
            self.s3.Bucket(bucket).put_object(Key=dst_path + filename, Body=buffer)
            return True
        except Exception as e:
            raise AwsS3Exception(str(e))


    def download(self, bucket, src_path, dst_path, filename):
        s3bucket = self.s3.Bucket(bucket)

        if not dst_path.endswith('/'):
            dst_path = dst_path + '/'

        try:
            with open(dst_path +  filename, 'wb') as f:
                s3bucket.download_fileobj(src_path, f)

            f.close()
        except Exception as e:
            raise AwsS3Exception(str(e))
