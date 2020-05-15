import React from "react";
import {Grid, Table, Segment} from "semantic-ui-react";
import Link from "found/lib/Link";
import { createPaginationContainer, graphql } from "react-relay";

class PublicJobList extends React.Component {
    constructor(props) {
        super(props);

        this.state = {
            order: 'last_updated',
            direction: 'ascending'
        }
    }

    // handleSort = (clickedColumn) => () => {
    //     // This is very inelegant
    //     const {order, direction} = this.state
    //     let newState = {}
    //     if (order !== clickedColumn) {
    //         newState = {
    //             order: clickedColumn,
    //             direction: 'ascending'
    //         }
    //     } else {
    //         newState = {
    //             order: order,
    //             direction: direction === 'ascending' ? 'descending' : 'ascending',
    //         }
    //     }
    //     this.setState(newState)
        
    //     const signedOrder = newState.direction === 'ascending' ? newState.order : '-' + newState.order
    //     this.props.handleSort(signedOrder)
    // }

    render() {
        console.log(this.props.data)
        this.rows = this.props.data.bilbyJobs.edges.map(({node}) => <TableRow key={node.id} id={node.id} name={node.name} description={node.description} lastUpdated={node.lastUpdated} jobStatus={node.jobStatus} {...this.props}/>)
        const {order, direction} = this.state
        return <React.Fragment>
            <Grid.Row>
                <Grid.Column>
                    <Segment style={{overflow: 'auto', maxHeight: 200}}>
                        <Table sortable fixed celled>
                            <Table.Header>
                                <Table.Row>
                                    {/* <Table.HeaderCell sorted={order === 'name' ? direction : null} onClick={this.handleSort('name')}>Name</Table.HeaderCell>
                                    <Table.HeaderCell sorted={order === 'description' ? direction : null} onClick={this.handleSort('description')}>Description</Table.HeaderCell>
                                    <Table.HeaderCell sorted={order === 'last_updated' ? direction : null} onClick={this.handleSort('last_updated')}>Edit Date</Table.HeaderCell>
                                    <Table.HeaderCell sorted={order === 'jobStatus' ? direction : null} onClick={this.handleSort('jobStatus')}>Job Status</Table.HeaderCell> */}
                                    <Table.HeaderCell>Name</Table.HeaderCell>
                                    <Table.HeaderCell>Description</Table.HeaderCell>
                                    <Table.HeaderCell>Status</Table.HeaderCell>
                                    <Table.HeaderCell>Actions</Table.HeaderCell>
                                </Table.Row>
                            </Table.Header>
                            <Table.Body>
                                {this.rows}
                            </Table.Body>
                        </Table>
                    </Segment>
                </Grid.Column>
            </Grid.Row>
        </React.Fragment>
    }
}

function TableRow(props) {
    const {id, name, description, lastUpdated, jobStatus, match, router} = props
    return (
        <Table.Row>
            <Table.Cell content={name}/>
            <Table.Cell content={description}/>
            <Table.Cell content={jobStatus}/>
            <Table.Cell>
                <Link to={{
                    pathname: '/bilby/job-results/',
                }} activeClassName="selected" exact match={match} router={router}>
                    View Results
                </Link>
            </Table.Cell>
        </Table.Row>
    )

}

// export default PublicJobList;
export default createPaginationContainer(PublicJobList,
    {
        data: graphql`
            fragment PublicJobList_data on Query {
                bilbyJobs(
                    first: $count,
                    after: $cursor,
                    orderBy: $orderBy
                ) @connection(key: "PublicJobList_bilbyJobs") {
                    edges {
                        node {
                            id
                            name
                            description
                            jobStatus
                        }
                    }
                  }
            }
        `,
    },
    {
        direction: 'forward',
        query: graphql`
            query PublicJobListForwardQuery(
                $count: Int!,
                $cursor: String,
                $orderBy: String
            ) {
              ...PublicJobList_data
            }
        `,
        getConnectionFromProps(props) {
            return props.data && props.data.bilbyJobs
        },

        getFragmentVariables(previousVariables, totalCount) {
            return {
                ...previousVariables,
                count: totalCount
            }
        },

        getVariables(props, {count, cursor}, {orderBy}) {
            return {
                count,
                cursor,
                orderBy,
            }
        }
    }
)