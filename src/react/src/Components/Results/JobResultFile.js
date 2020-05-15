import {createFragmentContainer, graphql} from "react-relay";
import React from "react";
import {Table} from "semantic-ui-react";
import filesize from 'filesize';

class JobResultFile extends React.Component {
    constructor(props) {
        super(props)
    }

    render() {
        return (
            <Table.Row>
                <Table.Cell>
                    {
                        this.props.bilbyResultFile.isDir ? this.props.bilbyResultFile.path : (
                            <a href={"https://gw-cloud.org/job/apiv1/file/?fileId=" + this.props.bilbyResultFile.downloadId}
                               target="_blank">
                                {this.props.bilbyResultFile.path}
                            </a>
                        )
                    }
                </Table.Cell>
                <Table.Cell content={this.props.bilbyResultFile.isDir ? "Directory" : "File"}/>
                <Table.Cell content={filesize(this.props.bilbyResultFile.fileSize, {round: 0})}/>
            </Table.Row>
        )
    }
}

export default createFragmentContainer(JobResultFile, {
    bilbyResultFile: graphql`
        fragment JobResultFile_bilbyResultFile on BilbyResultFile {
            path
            isDir
            fileSize
            downloadId
        }
    `
});