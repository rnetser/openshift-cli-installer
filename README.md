# openshift-cli-installer
Basic Openshift install CLI wrapper.  
The tool allows deploying or deletion of one or more clusters.  
The clusters can be deployed on different platforms; currently supported platforms: AWS IPI, ROSA and Hypershift.  
Each cluster can be provided with different configuration options, such as worker type, number of workers etc.

## Tools
* AWS IPI installation uses openshift-installer cli which is extracted from the cluster's target version.  
The binary is taken from `quay.io/openshift-release-dev/ocp-release:<target version>`
* ROSA and Hypershift installation uses the latest ROSA CLI

### Container
Image locate at [openshift-cli-installer](https://quay.io/repository/redhat_msi/openshift-cli-installer)  
To pull the image: `podman pull quay.io/openshift-cli-installer`

### Global CLI configuration
* `--clusters-install-data-directory`: Clusters configurations are written to `<clusters-install-data-directory><platform><cluster name>`; write permissions are needed.
    * `<cluster directory>/auth` contains `kubeconfig` and `kubeadmin-password` files
* `--parallel`: To create / destroy clusters in parallel
* Pass `--s3-bucket-name` (and optionally `--s3-bucket-path`) to backup <cluster directory> in an S3 bucket.  


* AWS IPI clusters:
  * The installer output is saved in the <cluster directory>.
  * The data is used for cluster destroy.
  * `base_domain` cluster parameter is mandatory
  * `--registry-config-file`: registry-config json file path, can be obtained from [openshift local cluster](https://console.redhat.com/openshift/create/local)

* ROSA / Hypershift clusters:
  * `--ocm-token`: OCM token, defaults to `OCM_TOKEN` environment variable.
  * `--ocm-env`: OCM environment to deploy the cluster; available options: `stage` or `production` (defaults to `stage`)

### Cluster parameters
Every call to the openshift installer cli must have at least one `--cluster` option.  

* Mandatory parameters:
  * name: The name of the cluster
  * version: The version of the cluster
  * platform: The platform to deploy the cluster on (supported platforms are: aws, rosa and hypershift)
  * region: The region to deploy the cluster
* Optional parameters:
  * To set cluster create / destroy timeout, pass `--cluster ...timeout=1h'`; default is 30 minutes.
  * `timeout` and `expiration-time` format examples: `1h`, `30m`, `3600s`
  * AWS IPI:
    * To overwrite cluster config, check [install-config-template.j2](app/manifests/install-config-template.j2) parameters.
    * Every parameter (marked with double curly brackets in the template) can be overwritten.
    * For example: to overwrite `{{ fips|default("false", true) }}` pass `--cluster '...fips=true'`
  * ROSA / Hypershift:
    * Every supported ROSA CLI create/delete parameter can be passed. Check `rosa create --help` for more details.
    * For example:
      * Pass `--cluster ...fips=true'` to enable FIPS
      * Pass `--cluster ...expiration-time=2h'` to have the cluster expiration time set to 2 hours

### Usages

```
podman run quay.io/redhat_msi/openshift-cli-installer --help
```

### Local run

Clone the [repository](https://github.com/RedHatQE/openshift-cli-installer)

```
git clone https://github.com/RedHatQE/openshift-cli-installer.git
```

Install [poetry](https://github.com/python-poetry/poetry)

Use `poetry run python app/cli.py` to execute the cli.

```
poetry install
poetry run python app/cli.py --help
```


### Create Clusters

Each command can be run via container `podman run quay.io/redhat_msi/openshift-cli-installer` or via poetry command `poetry run python app/cli.py`

#### One cluster
##### AWS IPI cluster

```
podman run quay.io/redhat_msi/openshift-cli-installer \
    --action create \
    --registry-config-file=registry-config.json \
    --clusters-install-data-directory=/tmp/ocp-clusters \
    --s3-bucket-name=openshift-cli-installer \
    --s3-bucket-path=install-folders \
    --cluster 'name=ipi1;base_domain=aws.interop.ccitredhat.com;platform=aws;region=us-east-2;version=4.14.0-ec.2;worker_flavor=m5.xlarge'
```

##### ROSA cluster

```
podman run quay.io/redhat_msi/openshift-cli-installer \
    --action create \
    --ocm-token=$OCM_TOKEN \
    --ocm-env=stage \
    --clusters-install-data-directory=/tmp/ocp-clusters \
    --cluster 'name=rosa1;platform=rosa;region=us-east-2;version=4.13.4;compute-machine-type=m5.xlarge;replicas=2;channel-group=candidate;expiration-time=4h;timeout=1h'
```

##### Hypershift cluster

```
podman run quay.io/redhat_msi/openshift-cli-installer \
    --action create \
    --ocm-token=$OCM_TOKEN \
    --ocm-env=stage \
    --clusters-install-data-directory=/tmp/ocp-clusters \
    --cluster 'name=hyper;platform=hypershift;region=us-west-2;version=4.13.4;compute-machine-type=m5.4xlarge;replicas=6;channel-group=candidate;expiration-time=4h;timeout=1h'
```

##### Multiple clusters

To run multiple clusters deployments in parallel pass -p,--parallel.

```
podman run quay.io/redhat_msi/openshift-cli-installer \
    --action create \
    --registry-config-file=registry-config.json \
    --clusters-install-data-directory=/tmp/ocp-clusters \
    --s3-bucket-name=openshift-cli-installer \
    --s3-bucket-path=install-folders \  
    --ocm-token=$OCM_TOKEN \
    --ocm-env=stage \
    --cluster 'name=hyper1;platform=hypershift;region=us-west-2;version=4.13.4;compute-machine-type=m5.4xlarge;replicas=6;channel-group=candidate;expiration-time=2h;timeout=1h' \
    --cluster 'name=ipi1;base_domain=aws.interop.ccitredhat.com;platform=aws;region=us-east-2;version=4.14.0-ec.2;worker_flavor=m5.xlarge' \
    --cluster 'name=rosa1;platform=rosa;region=us-east-2;version=4.13.4;compute-machine-type=m5.xlarge;replicas=2;channel-group=candidate;expiration-time=4h;timeout=1h' \
    --parallel
```

### Destroy Clusters
#### One cluster
##### AWS IPI cluster

```
podman run quay.io/redhat_msi/openshift-cli-installer \
    --action destroy \
    --ocm-token=$OCM_TOKEN \
    --ocm-env=stage \
    --clusters-install-data-directory=/tmp/ocp-clusters \
    --cluster 'name=ipi1;region=us-east-2;version=4.14.0-ec.2;timeout=1h'
```

##### ROSA cluster

```
podman run quay.io/redhat_msi/openshift-cli-installer \
    --action destroy \
    --ocm-token=$OCM_TOKEN \
    --ocm-env=stage \
    --clusters-install-data-directory=/tmp/ocp-clusters \
    --cluster 'name=rosa1;platform=rosa;region=us-east-2;version=4.13.4;timeout=1h'
```


##### Hypershift cluster

```
podman run quay.io/redhat_msi/openshift-cli-installer \
    --action destroy \
    --ocm-token=$OCM_TOKEN \
    --ocm-env=stage \
    --clusters-install-data-directory=/tmp/ocp-clusters \
    --cluster 'name=hyper1;platform=rosa;region=us-east-2;version=4.13.4;timeout=1h'
```

##### Multiple clusters

To run multiple clusters deletion in parallel pass -p,--parallel.

```
podman run quay.io/redhat_msi/openshift-cli-installer \
    --action destroy \
    --ocm-token=$OCM_TOKEN \
    --ocm-env=stage \
    --clusters-install-data-directory=/tmp/ocp-clusters \
    --cluster 'name=rosa1;platform=rosa;region=us-east-2;version=4.13.4;timeout=1h' \
    --cluster 'name=hyper1;platform=rosa;region=us-east-2;version=4.13.4;timeout=1h' \
    --cluster 'name=ipi1;region=us-east-2;version=4.14.0-ec.2;timeout=1h'
```
